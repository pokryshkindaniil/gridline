from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from ..config import get_settings
from ..db import get_db
from ..models import CalendarFeed, CalendarFeedSessionType, Event, Season, Series, Session, SessionChange
from ..ratelimit import feed_mutation_limit
from ..schemas import ChangeOut, FeedCreated, FeedIn, FeedOut, FeedPatch, SeriesOut
from ..services import feeds as svc

router = APIRouter()
DbDep = Annotated[Db, Depends(get_db)]


def _urls(token: str) -> tuple[str, str]:
    base = get_settings().public_api_base_url.rstrip("/")
    http = f"{base}/calendar/{token}.ics"
    return http, "webcal://" + http.split("://", 1)[1]


def _feed_out(feed: CalendarFeed) -> FeedOut:
    public, webcal = _urls(feed.public_token)
    return FeedOut(public_token=feed.public_token, public_url=public, webcal_url=webcal,
                   series=[SeriesOut.model_validate(s) for s in feed.series if s.public],
                   session_types=sorted(t.session_type for t in feed.session_types),
                   timezone=feed.timezone, include_emoji=feed.include_emoji,
                   created_at=feed.created_at, updated_at=feed.updated_at)


def get_feed_or_404(db: Db, token: str) -> CalendarFeed:
    feed = db.scalar(select(CalendarFeed).where(CalendarFeed.public_token == token))
    if feed is None:
        raise HTTPException(404, "feed not found")
    if feed.revoked_at is not None:
        raise HTTPException(410, "this feed has been revoked")
    return feed


def edit_token(x_edit_token: Annotated[str | None, Header()] = None) -> str | None:
    """Header only: query strings end up in proxy/CDN access logs, headers do not."""
    return x_edit_token


def require_owner(feed: CalendarFeed, token: str | None) -> None:
    if not svc.verify_edit_token(feed, token):
        raise HTTPException(403, "missing or invalid edit token")


@router.post("/feeds", response_model=FeedCreated, status_code=201, dependencies=[Depends(feed_mutation_limit)])
def create_feed(body: FeedIn, db: DbDep) -> FeedCreated:
    try:
        tz = svc.validate_timezone(body.timezone)
        series = svc.resolve_series(db, body.series)
        types = svc.validate_types(body.session_types)
    except svc.FeedError as exc:
        raise HTTPException(422, str(exc)) from exc
    secret = svc.new_edit_token()
    feed = CalendarFeed(public_token=svc.new_public_token(), edit_token_hash=svc.hash_token(secret), timezone=tz,
                        include_emoji=body.include_emoji)
    feed.series = series
    feed.session_types = [CalendarFeedSessionType(session_type=t) for t in types]
    db.add(feed)
    db.commit()
    public, webcal = _urls(feed.public_token)
    return FeedCreated(public_url=public, webcal_url=webcal, edit_url=f"/manage/{feed.public_token}?token={secret}",
                       public_token=feed.public_token, edit_token=secret)


@router.get("/feeds/{public_token}", response_model=FeedOut)
def read_feed(public_token: str, db: DbDep) -> FeedOut:
    return _feed_out(get_feed_or_404(db, public_token))


@router.patch("/feeds/{public_token}", response_model=FeedOut, dependencies=[Depends(feed_mutation_limit)])
def update_feed(public_token: str, body: FeedPatch, db: DbDep, token: Annotated[str | None, Depends(edit_token)]) -> FeedOut:
    feed = get_feed_or_404(db, public_token)
    require_owner(feed, token)
    try:
        if body.timezone is not None:
            feed.timezone = svc.validate_timezone(body.timezone)
        if body.include_emoji is not None:
            feed.include_emoji = body.include_emoji
        if body.series is not None:
            feed.series = svc.resolve_series(db, body.series)
        if body.session_types is not None:
            types = svc.validate_types(body.session_types)
            feed.session_types = [CalendarFeedSessionType(session_type=t) for t in types]
    except svc.FeedError as exc:
        raise HTTPException(422, str(exc)) from exc
    feed.updated_at = datetime.now(UTC)
    db.commit()
    return _feed_out(feed)


@router.delete("/feeds/{public_token}", status_code=204, dependencies=[Depends(feed_mutation_limit)])
def revoke_feed(public_token: str, db: DbDep, token: Annotated[str | None, Depends(edit_token)]) -> Response:
    feed = get_feed_or_404(db, public_token)
    require_owner(feed, token)
    feed.revoked_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


@router.get("/feeds/{public_token}/changes", response_model=list[ChangeOut])
def feed_changes(public_token: str, db: DbDep, limit: Annotated[int, Query(le=100)] = 20) -> list[ChangeOut]:
    """Recent schedule changes affecting sessions this feed includes."""
    feed = get_feed_or_404(db, public_token)
    stmt = (
        select(SessionChange, Session, Event, Series)
        .join(Session, SessionChange.session_id == Session.id).join(Event, Session.event_id == Event.id)
        .join(Season, Event.season_id == Season.id).join(Series, Season.series_id == Series.id)
        .where(Series.id.in_([s.id for s in feed.series if s.public]),
               Session.session_type.in_([t.session_type for t in feed.session_types]))
        .order_by(SessionChange.detected_at.desc()).limit(limit)
    )
    return [ChangeOut(detected_at=c.detected_at, session_id=s.id, series_short_name=sr.short_name, event_name=e.name,
                      session_name=s.name, field_name=c.field_name, old_value=c.old_value, new_value=c.new_value,
                      source_url=c.source_url) for c, s, e, sr in db.execute(stmt)]


@router.get("/calendar/{filename}")
def calendar_ics(filename: str, request: Request, db: DbDep) -> Response:
    if not filename.endswith(".ics"):
        raise HTTPException(404, "not found")
    feed = get_feed_or_404(db, filename.removesuffix(".ics"))
    body = svc.render_feed(db, feed)
    etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:24] + '"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=300",
               "Content-Disposition": f'inline; filename="gridline-{feed.public_token}.ics"'}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="text/calendar; charset=utf-8", headers=headers)
