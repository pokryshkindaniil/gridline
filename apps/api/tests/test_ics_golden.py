"""RFC 5545 hardening: golden snapshots, multi-revision stability and structural invariants.

Regenerate snapshots deliberately with:  UPDATE_GOLDEN=1 pytest tests/test_ics_golden.py
"""

import os
import re
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from gridline_calendar import CalendarEvent, render_calendar
from gridline_shared import SessionStatus, SessionType

GOLDEN = Path(__file__).parent / "golden"
IDS = [uuid.UUID(int=i) for i in (1, 2, 3)]


def v1() -> list[CalendarEvent]:
    mk = lambda i, series, event, name, typ, start, end=None: CalendarEvent(  # noqa: E731
        session_id=IDS[i], series_short_name=series, event_name=event, session_name=name, session_type=typ,
        status=SessionStatus.SCHEDULED, start_at=start, end_at=end, sequence=0,
        last_modified=datetime(2026, 9, 1, 8, 0, tzinfo=UTC), source_name="Official source",
        source_url="https://example.org/schedule", checked_at=datetime(2026, 9, 1, 8, 5, tzinfo=UTC),
        location="Circuit; Name, Town", event_timezone="Europe/Madrid",
    )
    return [
        mk(0, "WEC", "6 Hours of Spa", "Race", SessionType.RACE, datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
           datetime(2026, 10, 3, 18, 0, tzinfo=UTC)),
        mk(1, "F1", "Singapore Grand Prix", "Qualifying", SessionType.QUALIFYING, datetime(2026, 10, 10, 13, 0, tzinfo=UTC)),
        mk(2, "GTWC", "Ünïcødé — Östersund, Ré; backslash\\ test", "Free Practice 1 ✓", SessionType.PRACTICE,
           datetime(2026, 10, 2, 7, 0, tzinfo=UTC), datetime(2026, 10, 2, 8, 0, tzinfo=UTC)),
    ]


def v2() -> list[CalendarEvent]:  # race moved 30 min later
    evs = v1()
    evs[0] = replace(evs[0], start_at=evs[0].start_at + timedelta(minutes=30), sequence=1,
                     last_modified=datetime(2026, 9, 5, 9, 0, tzinfo=UTC), checked_at=datetime(2026, 9, 5, 9, 5, tzinfo=UTC))
    return evs


def v3() -> list[CalendarEvent]:  # qualifying cancelled
    evs = v2()
    evs[1] = replace(evs[1], status=SessionStatus.CANCELLED, sequence=1,
                     last_modified=datetime(2026, 9, 9, 10, 0, tzinfo=UTC), checked_at=datetime(2026, 9, 9, 10, 5, tzinfo=UTC))
    return evs


def render(evs):
    return render_calendar(evs, name="GRIDLINE motorsport", timezone="Europe/Berlin")


@pytest.mark.parametrize("name,evs", [("v1", v1), ("v2", v2), ("v3", v3)])
def test_golden_snapshot(name, evs):
    out = render(evs())
    path = GOLDEN / f"feed_{name}.ics"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_bytes(out.encode())
    assert out.encode() == path.read_bytes(), f"{path.name} differs; if intended run with UPDATE_GOLDEN=1"


def props(ics: str) -> list[dict[str, str]]:
    out, cur = [], None
    for line in ics.replace("\r\n ", "").split("\r\n"):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            out.append(cur)
            cur = None
        elif cur is not None:
            k, v = line.split(":", 1)
            cur[k] = v
    return out


def test_uid_constant_and_sequence_monotonic_over_revisions():
    revisions = [props(render(f())) for f in (v1, v2, v3)]
    uids = [[e["UID"] for e in r] for r in revisions]
    assert uids[0] == uids[1] == uids[2] and len(set(uids[0])) == 3
    for uid in uids[0]:
        seqs = [int(next(e for e in r if e["UID"] == uid)["SEQUENCE"]) for r in revisions]
        assert seqs == sorted(seqs)
    by_uid = lambda r, i: next(e for e in r if e["UID"].endswith(f"{IDS[i]}@gridline"))  # noqa: E731
    assert by_uid(revisions[0], 0)["DTSTART"] != by_uid(revisions[1], 0)["DTSTART"]
    assert by_uid(revisions[2], 1)["STATUS"] == "CANCELLED" and by_uid(revisions[1], 1)["STATUS"] == "CONFIRMED"
    assert by_uid(revisions[2], 1)["SEQUENCE"] > by_uid(revisions[0], 1)["SEQUENCE"]
    assert by_uid(revisions[2], 1)["LAST-MODIFIED"] > by_uid(revisions[0], 1)["LAST-MODIFIED"]


def test_rfc5545_structure():
    out = render(v3())
    assert out.endswith("\r\n") and "\r\n\r\n" not in out
    assert "\n" not in out.replace("\r\n", "") and "\r" not in out.replace("\r\n", "")
    for raw in out.split("\r\n")[:-1]:
        assert len(raw.encode()) <= 75 and raw != ""
    lines = out.replace("\r\n ", "").split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR"
    assert {"VERSION:2.0", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"} <= set(lines)
    for e in props(out):
        for required in ("UID", "DTSTAMP", "DTSTART", "DTEND", "SEQUENCE", "LAST-MODIFIED", "SUMMARY", "STATUS"):
            assert required in e, required
        assert re.fullmatch(r"\d{8}T\d{6}Z", e["DTSTAMP"]) and re.fullmatch(r"\d{8}T\d{6}Z", e["DTSTART"])
        assert e["DTEND"] > e["DTSTART"]


def test_text_escaping():
    text = render(v1()).replace("\r\n ", "")
    assert r"LOCATION:Circuit\; Name\, Town" in text
    summary = next(ln for ln in text.split("\r\n") if ln.startswith("SUMMARY:GTWC"))
    assert r"Östersund\, Ré\; backslash\\ test" in summary
    # no unescaped commas/semicolons survive in TEXT values
    assert not re.search(r"(?<!\\)[;,]", summary.split(":", 1)[1])


def test_ordering_is_deterministic_and_input_order_independent():
    a = render(v1())
    b = render(list(reversed(v1())))
    assert a == b
    starts = [e["DTSTART"] for e in props(a)]
    assert starts == sorted(starts)


def test_duplicate_uids_are_refused():
    with pytest.raises(ValueError, match="duplicate"):
        render([v1()[0], v1()[0]])
