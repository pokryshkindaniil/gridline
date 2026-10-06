"""End-to-end acceptance path (spec section 18) against a real database."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from gridline_shared import SessionStatus
from gridline_sources import get_source
from sqlalchemy import select

from app.models import Event, Session, SessionChange
from app.services.sync import apply_parsed_sessions

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def vevents(ics: str) -> list[dict[str, str]]:
    out, cur = [], None
    for line in ics.replace("\r\n ", "").split("\r\n"):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            out.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            k, v = line.split(":", 1)
            cur[k.split(";")[0]] = v
    return out


def create_feed(client):
    r = client.post("/feeds", json={"series": ["formula-1", "fia-wec", "gt-world-challenge-europe"],
                                   "session_types": ["qualifying", "sprint", "race"], "timezone": "Europe/Madrid"})
    assert r.status_code == 201, r.text
    return r.json()


def test_full_acceptance_flow(client, db, seeded):
    feed = create_feed(client)
    assert feed["webcal_url"].startswith("webcal://") and feed["public_url"].endswith(f"{feed['public_token']}.ics")
    assert feed["edit_token"] not in feed["public_url"]
    assert feed["edit_url"] == f"/manage/{feed['public_token']}?token={feed['edit_token']}"

    path = f"/calendar/{feed['public_token']}.ics"
    r = client.get(path)
    assert r.headers["content-type"].startswith("text/calendar")
    before = vevents(r.text)
    assert before
    summaries = " ".join(e["SUMMARY"] for e in before)
    assert "GTWC" in summaries and "F1" in summaries and "WEC" in summaries
    assert not any("Practice" in e["SUMMARY"] or "IMSA" in e["SUMMARY"] for e in before)  # filters respected

    # 12. change the start time of an existing session
    target = db.scalar(select(Session).join(Event).where(Event.external_id == "e254", Session.external_id == "race-1"))
    src = get_source("gt_world_challenge")
    parsed = src.parse(src.load_fixture()).sessions
    moved = [replace(p, start_at=p.start_at + timedelta(minutes=30))
             if (p.event_external_id, p.external_id) == ("e254", "race-1") else p for p in parsed]
    apply_parsed_sessions(db, series_map(db), moved, source_name=target.source_name, now=NOW + timedelta(hours=1))
    db.commit()

    # 13-15. regenerate: same UID, new DTSTART, no duplicates
    after = vevents(client.get(path).text)
    uid = f"session-{target.id}@gridline"
    b = next(e for e in before if e["UID"] == uid)
    a = next(e for e in after if e["UID"] == uid)
    assert a["DTSTART"] != b["DTSTART"] and int(a["SEQUENCE"]) == int(b["SEQUENCE"]) + 1
    assert len(after) == len(before)
    assert len({e["UID"] for e in after}) == len(after)

    # 16. SessionChange recorded
    ch = db.scalar(select(SessionChange).where(SessionChange.session_id == target.id))
    assert ch.field_name == "start_at"
    changes = client.get(f"/feeds/{feed['public_token']}/changes").json()
    assert changes[0]["field_name"] == "start_at" and changes[0]["session_name"] == "Race 1"

    # 17. freshness/source information exposed
    sess = client.get("/sessions", params={"series": "gt-world-challenge-europe", "limit": 1}).json()[0]
    assert sess["checked_at"] and sess["source_url"] and sess["source_name"]
    health = {h["source_id"]: h for h in client.get("/sources/health").json()}
    assert health["formula1"]["status"] == "stale"
    assert "imsa" not in health  # switched off: no public source-health row either


def series_map(db):
    from app.catalog import ensure_series
    return ensure_series(db)["gt-world-challenge-europe"]


def test_etag_conditional_get(client, seeded):
    feed = create_feed(client)
    r1 = client.get(f"/calendar/{feed['public_token']}.ics")
    r2 = client.get(f"/calendar/{feed['public_token']}.ics", headers={"If-None-Match": r1.headers["etag"]})
    assert r2.status_code == 304


def test_feed_management_requires_edit_token(client, seeded):
    feed = create_feed(client)
    tok = feed["public_token"]
    assert client.patch(f"/feeds/{tok}", json={"timezone": "UTC"}).status_code == 403
    assert client.patch(f"/feeds/{tok}", json={"timezone": "UTC"}, headers={"X-Edit-Token": "nope"}).status_code == 403
    r = client.patch(f"/feeds/{tok}", headers={"X-Edit-Token": feed["edit_token"]},
                     json={"series": ["formula-1"], "session_types": ["race"], "timezone": "Asia/Tokyo",
                           "include_emoji": True})
    assert r.status_code == 200
    body = r.json()
    assert [s["slug"] for s in body["series"]] == ["formula-1"] and body["session_types"] == ["race"]
    assert body["timezone"] == "Asia/Tokyo" and body["include_emoji"] is True
    evs = vevents(client.get(f"/calendar/{tok}.ics").text)
    assert evs and all(e["SUMMARY"].startswith("🏁 F1") and e["SUMMARY"].endswith("Race") for e in evs)

    assert client.delete(f"/feeds/{tok}").status_code == 403
    assert client.delete(f"/feeds/{tok}", headers={"X-Edit-Token": feed["edit_token"]}).status_code == 204
    assert client.get(f"/calendar/{tok}.ics").status_code == 410
    assert client.get(f"/feeds/{tok}").status_code == 410


def test_feed_validation(client, seeded):
    bad = [{"series": ["nope"], "session_types": ["race"]}, {"series": ["formula-1"], "session_types": ["nope"]},
           {"series": ["formula-1"], "session_types": ["race"], "timezone": "Mars/Olympus"},
           {"series": [], "session_types": ["race"]}]
    for body in bad:
        assert client.post("/feeds", json=body).status_code == 422, body
    assert client.get("/calendar/doesnotexist.ics").status_code == 404
    assert client.get("/calendar/abc.txt").status_code == 404


def test_cancelled_session_in_feed(client, db, seeded):
    feed = create_feed(client)
    s = db.scalar(select(Session).join(Event).where(Event.external_id == "e254", Session.external_id == "race-2"))
    s.status = "cancelled"
    db.commit()
    ev = next(e for e in vevents(client.get(f"/calendar/{feed['public_token']}.ics").text)
              if e["UID"] == f"session-{s.id}@gridline")
    assert ev["STATUS"] == "CANCELLED" and ev["SUMMARY"].startswith("CANCELLED:")


def test_weekend_and_filters(client, seeded):
    w = client.get("/weekend", params={"at": "2026-10-04T10:00:00Z", "tz": "Europe/Madrid"}).json()
    assert (w["start_date"], w["end_date"]) == ("2026-10-02", "2026-10-04")
    assert w["session_count"] == len(w["sessions"]) > 0
    shown = {s["series"]["short_name"].lower() for s in w["sessions"]}
    assert "gtwc" in shown and "imsa" not in shown  # IMSA has weekend sessions in its fixture but is not public
    starts = [s["start_at"] for s in w["sessions"]]
    assert starts == sorted(starts)
    # Monday rolls to the upcoming weekend
    nxt = client.get("/weekend", params={"at": "2026-10-05T10:00:00Z"}).json()
    assert nxt["start_date"] == "2026-10-09"

    races = client.get("/sessions", params=[("series", "formula-1"), ("session_type", "race"),
                                            ("from", "2026-10-01T00:00:00Z")]).json()
    assert races and all(s["session_type"] == "race" and s["series"]["slug"] == "formula-1" for s in races)


def test_series_events_and_session_listing(client, seeded):
    series = client.get("/series").json()
    assert {s["slug"] for s in series if s["active"]} == {"formula-1", "fia-wec", "gt-world-challenge-europe"}
    assert "imsa-weathertech" not in {s["slug"] for s in series}
    events = client.get("/series/gt-world-challenge-europe/events").json()
    barcelona = next(e for e in events if e["name"] == "Barcelona")
    sessions = client.get(f"/events/{barcelona['id']}/sessions").json()
    assert {"Race 1", "Race 2"} <= {s["name"] for s in sessions}
    assert client.get(f"/events/{barcelona['id']}").json()["timezone"] == "Europe/Madrid"
    assert client.get("/series/nope").status_code == 404


def test_feed_over_three_revisions_keeps_uid_and_monotonic_sequence(client, db, seeded):
    feed = create_feed(client)
    path = f"/calendar/{feed['public_token']}.ics"
    src = get_source("gt_world_challenge")
    base = [p for p in src.parse(src.load_fixture()).sessions]
    target = ("e254", "race-1")

    def revise(**changes):
        sessions = [replace(p, **changes) if (p.event_external_id, p.external_id) == target else p for p in base]
        return apply_parsed_sessions(db, series_map(db), sessions, source_name="GT World Challenge Europe (SRO) (fixture snapshot)",
                                     now=NOW + timedelta(hours=len(history) + 1))

    def snapshot():
        db.commit()
        evs = {e["UID"]: e for e in vevents(client.get(path).text)}
        row = db.scalar(select(Session).join(Event).where(Event.external_id == "e254", Session.external_id == "race-1"))
        return evs[f"session-{row.id}@gridline"], len(evs)

    history = [snapshot()]
    original = next(p for p in base if (p.event_external_id, p.external_id) == target)
    revise(start_at=original.start_at + timedelta(minutes=30))
    history.append(snapshot())
    revise(start_at=original.start_at + timedelta(hours=1))
    history.append(snapshot())
    revise(start_at=original.start_at + timedelta(hours=1), status=SessionStatus.CANCELLED)
    history.append(snapshot())

    seqs = [int(h[0]["SEQUENCE"]) for h in history]
    assert seqs == sorted(seqs) and len(set(seqs)) == 4  # strictly increasing for 4 revisions
    assert len({h[0]["UID"] for h in history}) == 1 and len({h[1] for h in history}) == 1  # same UID, same count
    assert [h[0]["STATUS"] for h in history] == ["CONFIRMED"] * 3 + ["CANCELLED"]
    dtstarts = [h[0]["DTSTART"] for h in history]
    assert len(set(dtstarts)) == 3 and dtstarts[2] == dtstarts[3]
