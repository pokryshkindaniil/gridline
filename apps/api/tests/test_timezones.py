"""Timezone correctness: DB is UTC, conversion only at the boundaries, unknown zones are never guessed."""

import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from gridline_calendar import CalendarEvent, render_calendar
from gridline_shared import SessionStatus, SessionType
from gridline_sources import ParsedSession, RawSchedule, get_source
from gridline_sources.gt_world_challenge.parser import _offset
from sqlalchemy import select

from app.models import Session
from app.services.sync import apply_parsed_sessions


def ev(start: datetime, tz: str, user_tz: str = "UTC"):
    e = CalendarEvent(
        session_id="x", series_short_name="S", event_name="E", session_name="Race", session_type=SessionType.RACE,
        status=SessionStatus.SCHEDULED, start_at=start, end_at=None, sequence=0, last_modified=start,
        source_name="src", source_url="https://example.org", checked_at=start, event_timezone=tz,
    )
    ics = render_calendar([e], timezone=user_tz).replace("\r\n ", "")
    return {k: v for k, v in (ln.split(":", 1) for ln in ics.split("\r\n") if ":" in ln)}, ics


def local(ics: str, label: str) -> str:
    return re.search(rf"{label}: (\d\d:\d\d) \(([^)]+)\)", ics.replace("\\n", "\n"))[1]


# (instant UTC, circuit zone, expected circuit-local HH:MM)
CASES = [
    # Europe: DST ends Sun 2026-10-25 01:00Z (CEST -> CET)
    (datetime(2026, 10, 24, 12, 0, tzinfo=UTC), "Europe/Madrid", "14:00"),
    (datetime(2026, 10, 26, 13, 0, tzinfo=UTC), "Europe/Madrid", "14:00"),
    (datetime(2026, 3, 28, 12, 0, tzinfo=UTC), "Europe/Paris", "13:00"),   # winter
    (datetime(2026, 6, 13, 16, 0, tzinfo=UTC), "Europe/Paris", "18:00"),   # summer (Le Mans)
    # Asia: no DST
    (datetime(2026, 9, 27, 2, 0, tzinfo=UTC), "Asia/Tokyo", "11:00"),
    (datetime(2026, 10, 11, 12, 0, tzinfo=UTC), "Asia/Singapore", "20:00"),
    # Americas: DST ends Sun 2026-11-01 06:00Z
    (datetime(2026, 10, 31, 16, 0, tzinfo=UTC), "America/New_York", "12:00"),
    (datetime(2026, 11, 2, 17, 0, tzinfo=UTC), "America/New_York", "12:00"),
    (datetime(2026, 9, 6, 18, 0, tzinfo=UTC), "America/Chicago", "13:00"),
    (datetime(2026, 11, 8, 17, 0, tzinfo=UTC), "America/Sao_Paulo", "14:00"),
    # crossing midnight UTC
    (datetime(2026, 10, 3, 16, 30, tzinfo=UTC), "Asia/Tokyo", "01:30"),
    (datetime(2026, 10, 4, 0, 30, tzinfo=UTC), "America/New_York", "20:30"),
]


@pytest.mark.parametrize("start,tz,expected", CASES)
def test_circuit_local_time_is_correct_across_regions_and_dst(start, tz, expected):
    _, ics = ev(start, tz, user_tz="UTC")
    assert local(ics, "Circuit time") == expected


def test_user_timezone_rendering_and_utc_dtstart():
    props, ics = ev(datetime(2026, 10, 25, 0, 30, tzinfo=UTC), "Europe/Madrid", user_tz="America/New_York")
    assert props["DTSTART"] == "20261025T003000Z"  # always UTC on the wire
    assert "Starts: Sat 24 Oct 20:30 (America/New_York)" in ics.replace("\\n", "\n")  # EDT, before US DST end
    assert local(ics, "Circuit time") == "02:30"  # 00:30Z is still CEST (+2)


def test_gtwc_offset_helper_handles_midnight_and_dst():
    assert _offset((0, 30), (22, 30)).total_seconds() == 7200   # local day is ahead of GMT day
    assert _offset((23, 30), (1, 30)).total_seconds() == -7200  # local behind GMT across midnight


def test_naive_or_unknown_timezones_are_rejected_at_the_model_boundary():
    base = dict(season_year=2026, event_external_id="e", event_name="E", external_id="s", session_name="S",
                session_type=SessionType.RACE, source_url="https://x")
    with pytest.raises(ValueError, match="timezone-aware"):
        ParsedSession(timezone="Europe/Rome", start_at=datetime(2026, 1, 1, 12), **base)
    with pytest.raises(ValueError, match="invalid IANA"):
        ParsedSession(timezone="Mars/Olympus", start_at=datetime(2026, 1, 1, tzinfo=UTC), **base)
    with pytest.raises(ValueError, match="invalid IANA"):
        ParsedSession(timezone="", start_at=datetime(2026, 1, 1, tzinfo=UTC), **base)


def _gtwc_with(mutate):
    src = get_source("gt_world_challenge")
    raw = src.load_fixture()
    docs = {k: mutate(v) if k == "event_254.html" else v for k, v in raw.documents.items()}
    return src.parse(RawSchedule(raw.source_url, raw.fetched_at, docs, True))


def test_gtwc_unknown_country_is_quarantined_not_defaulted_to_utc():
    result = _gtwc_with(lambda h: h.replace("Spain", "Atlantis"))
    assert any("Atlantis" in i.message for i in result.issues)
    assert not any(s.event_external_id == "e254" for s in result.sessions)
    assert all(s.timezone != "UTC" for s in result.sessions)


def test_f1_missing_or_inconsistent_timezone_is_quarantined():
    src = get_source("formula1")
    raw = src.load_fixture()
    no_tz = {k: re.sub(r'timezone\\?":\\?"[^"\\]*\\?"', "tz_removed", v) if k == "race_singapore.html" else v
             for k, v in raw.documents.items()}
    result = src.parse(RawSchedule(raw.source_url, raw.fetched_at, no_tz, True))
    assert any("timezone" in i.message and i.event == "race_singapore.html" for i in result.issues)
    wrong = {k: v.replace("Asia/Singapore", "Europe/London") if k == "race_singapore.html" else v
             for k, v in raw.documents.items()}
    result = src.parse(RawSchedule(raw.source_url, raw.fetched_at, wrong, True))
    assert any("disagrees" in i.message for i in result.issues)


def test_wec_utc_only_ics_for_unmapped_circuit_is_quarantined():
    src = get_source("fia_wec")
    raw = src.load_fixture()
    docs = dict(raw.documents)
    docs["race_atlantis-1000-2026.html"] = docs["race_24-hours-of-le-mans-2026.html"]
    docs["race_atlantis-1000-2026.ics"] = docs["race_24-hours-of-le-mans-2026.ics"]
    result = src.parse(RawSchedule(raw.source_url, raw.fetched_at, docs, True))
    assert [i.event for i in result.issues] == ["atlantis-1000-2026"]
    assert "not in the circuit timezone map" in result.issues[0].message


def test_db_stores_utc_whatever_the_input_zone(db, series):
    tokyo = datetime(2026, 10, 4, 1, 30, tzinfo=ZoneInfo("Asia/Tokyo"))  # crosses UTC midnight backwards
    p = ParsedSession(season_year=2026, event_external_id="e", event_name="E", timezone="Asia/Tokyo",
                      external_id="s", session_name="Race", session_type=SessionType.RACE, start_at=tokyo,
                      source_url="https://x", event_start_date=date(2026, 10, 2), event_end_date=date(2026, 10, 4))
    apply_parsed_sessions(db, series["formula-1"], [p], source_name="t")
    db.commit()
    row = db.scalar(select(Session))
    assert row.start_at == datetime(2026, 10, 3, 16, 30, tzinfo=UTC) and row.start_at.utcoffset().total_seconds() == 0


def test_legacy_iana_aliases_used_by_sources_resolve():
    """F1 publishes 'US/Central'; slim container images only have it via the tzdata package."""
    from importlib.metadata import version

    assert ZoneInfo("US/Central").utcoffset(datetime(2026, 10, 25, 18, tzinfo=UTC)) is not None
    assert version("tzdata")
