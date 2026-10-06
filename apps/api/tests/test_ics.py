import re
from datetime import UTC, datetime
from uuid import uuid4

from gridline_calendar import CalendarEvent, render_calendar, uid_for_session
from gridline_shared import SessionStatus, SessionType


def make(**kw) -> CalendarEvent:
    base = dict(
        session_id=uuid4(), series_short_name="WEC", event_name="6 Hours of Spa", session_name="Race",
        session_type=SessionType.RACE, status=SessionStatus.SCHEDULED,
        start_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC), end_at=None, sequence=0,
        last_modified=datetime(2026, 4, 1, tzinfo=UTC), source_name="FIA WEC", source_url="https://www.fiawec.com",
        checked_at=datetime(2026, 4, 2, 10, 30, tzinfo=UTC), location="Spa, Francorchamps", event_timezone="Europe/Brussels",
    )
    return CalendarEvent(**{**base, **kw})


def unfold(ics: str) -> list[str]:
    return ics.replace("\r\n ", "").split("\r\n")


def test_valid_structure_and_crlf():
    ics = render_calendar([make()], timezone="Europe/Berlin")
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "\n" not in ics.replace("\r\n", "")
    lines = unfold(ics)
    assert lines.count("BEGIN:VEVENT") == lines.count("END:VEVENT") == 1
    assert "VERSION:2.0" in lines and any(ln.startswith("PRODID:") for ln in lines)
    for raw in ics.split("\r\n"):
        assert len(raw.encode()) <= 75


def test_summary_format_and_escaping():
    ics = unfold(render_calendar([make()]))
    assert "SUMMARY:WEC · 6 Hours of Spa · Race" in ics
    assert any(ln.startswith("LOCATION:Spa\\, Francorchamps") for ln in ics)
    desc = next(ln for ln in ics if ln.startswith("DESCRIPTION:"))
    assert "Official schedule" in desc and "Source: FIA WEC" in desc and "Verified: 2026-04-02 10:30 UTC" in desc


def test_uid_stable_when_time_changes_and_sequence_increments():
    sid = uuid4()
    a = unfold(render_calendar([make(session_id=sid)]))
    b = unfold(render_calendar([make(session_id=sid, start_at=datetime(2026, 5, 9, 12, 30, tzinfo=UTC),
                                     sequence=1, last_modified=datetime(2026, 4, 5, tzinfo=UTC))]))
    def uid(lines):
        return next(ln for ln in lines if ln.startswith("UID:"))

    assert uid(a) == uid(b) == f"UID:{uid_for_session(sid)}"
    assert "DTSTART:20260509T120000Z" in a and "DTSTART:20260509T123000Z" in b
    assert "SEQUENCE:0" in a and "SEQUENCE:1" in b
    assert sum(ln == "BEGIN:VEVENT" for ln in b) == 1  # no duplicate


def test_cancelled_session():
    ics = unfold(render_calendar([make(status=SessionStatus.CANCELLED)]))
    assert "STATUS:CANCELLED" in ics
    assert any(ln.startswith("SUMMARY:CANCELLED: WEC") for ln in ics)


def test_default_duration_when_end_missing():
    ics = unfold(render_calendar([make(session_type=SessionType.RACE)]))
    assert "DTEND:20260509T140000Z" in ics  # race defaults to 2h


def test_timezone_handling_across_dst():
    # 2026-03-28 12:00Z is before EU DST (CET, +1); 2026-04-04 12:00Z is after (CEST, +2).
    winter = make(start_at=datetime(2026, 3, 28, 12, 0, tzinfo=UTC))
    summer = make(start_at=datetime(2026, 4, 4, 12, 0, tzinfo=UTC))
    ics = unfold(render_calendar([winter, summer], timezone="Europe/Berlin"))
    starts = [ln for ln in ics if ln.startswith("DESCRIPTION:")]
    assert "Starts: Sat 28 Mar 13:00 (Europe/Berlin)" in starts[0]
    assert "Starts: Sat 4 Apr 14:00 (Europe/Berlin)" in starts[1]
    assert "Circuit time: 14:00 (Europe/Brussels)" in starts[0] or "Circuit time" in starts[0]
    assert "X-WR-TIMEZONE:Europe/Berlin" in ics
    assert all(re.fullmatch(r"DT(START|END):\d{8}T\d{6}Z", ln) for ln in ics if ln.startswith(("DTSTART", "DTEND")))


def test_long_unicode_lines_fold_without_breaking_characters():
    ics = render_calendar([make(event_name="Ü" * 80)])
    assert "Ü" * 80 in "".join(unfold(ics))


def test_optional_session_emoji_prefixes():
    cases = [
        (SessionType.PRACTICE, "🧪"),
        (SessionType.QUALIFYING, "⏱️"),
        (SessionType.SPRINT, "🏁"),
        (SessionType.RACE, "🏁"),
        (SessionType.WARMUP, "🔥"),
        (SessionType.TEST, "🧪"),
    ]
    for session_type, emoji in cases:
        lines = unfold(render_calendar([make(session_type=session_type, session_name=session_type.value.title())], include_emoji=True))
        assert any(line.startswith(f"SUMMARY:{emoji} WEC · 6 Hours of Spa ·") for line in lines)

    plain = unfold(render_calendar([make(session_type=SessionType.RACE)], include_emoji=False))
    assert "SUMMARY:WEC · 6 Hours of Spa · Race" in plain
    other = unfold(render_calendar([make(session_type=SessionType.OTHER, session_name="Drivers briefing")], include_emoji=True))
    assert "SUMMARY:WEC · 6 Hours of Spa · Drivers briefing" in other
