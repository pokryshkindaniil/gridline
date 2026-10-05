import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from gridline_shared import SessionType, classify_session_type
from gridline_sources import get_source
from gridline_sources.gt_world_challenge.parser import _offset


def _parse(source_id: str):
    src = get_source(source_id)
    result = src.parse(src.load_fixture())
    assert result.issues == [], result.issues
    return result.sessions


@pytest.mark.parametrize("name,expected", [
    ("Free Practice 1", SessionType.PRACTICE), ("Practice 3", SessionType.PRACTICE),
    ("Qualifying 1 - Group A", SessionType.QUALIFYING), ("Hyperpole", SessionType.QUALIFYING),
    ("Sprint Qualifying", SessionType.QUALIFYING), ("Sprint", SessionType.SPRINT),
    ("Race 2", SessionType.RACE), ("Main Race", SessionType.RACE), ("Warm-up", SessionType.WARMUP),
    ("Bronze Test", SessionType.TEST), ("Pit Lane Walk", SessionType.OTHER),
])
def test_classify(name, expected):
    assert classify_session_type(name) == expected


def test_gtwc_barcelona_times_are_utc_and_timezone_is_circuit_local():
    sessions = [s for s in _parse("gt_world_challenge") if s.event_external_id == "e254"]
    race1 = next(s for s in sessions if s.external_id == "race-1")
    assert race1.start_at == datetime(2026, 10, 3, 12, 0, tzinfo=UTC)  # 14:00 local CEST, GMT column 12:00
    assert race1.timezone == "Europe/Madrid"
    assert race1.start_at.astimezone(ZoneInfo("Europe/Madrid")).hour == 14
    assert race1.session_type == SessionType.RACE
    assert race1.circuit_name == "Circuit de Barcelona - Catalunya"
    assert {"qualifying-1-group-a", "free-practice-1", "race-2"} <= {s.external_id for s in sessions}


def test_gtwc_offset_across_midnight():
    assert _offset((0, 30), (23, 30)).total_seconds() == 3600  # local is after GMT's previous day
    assert _offset((14, 0), (12, 0)).total_seconds() == 7200


def test_session_identity_contains_no_time():
    for sid in ("formula1", "gt_world_challenge", "fia_wec", "imsa"):
        for s in _parse(sid):
            assert not re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|\d{2}h\d{2}", s.external_id), s.external_id
            assert s.start_at.tzinfo is not None


def test_session_identities_unique_per_event():
    for sid in ("formula1", "gt_world_challenge", "fia_wec", "imsa"):
        parsed = _parse(sid)
        keys = [(p.season_year, p.event_external_id, p.external_id) for p in parsed]
        assert len(keys) == len(set(keys))


def test_f1_official_sprint_weekend():
    sg = [s for s in _parse("formula1") if s.event_external_id == "singapore"]
    kinds = {s.external_id: s.session_type for s in sg}
    assert kinds["sprint"] == SessionType.SPRINT
    assert kinds["sprint-qualifying"] == SessionType.QUALIFYING
    assert kinds["race"] == SessionType.RACE
    race = next(s for s in sg if s.external_id == "race")
    assert race.start_at == datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
    assert race.timezone == "Asia/Singapore" and race.event_name == "Singapore Grand Prix"
    assert race.start_at.astimezone(ZoneInfo(race.timezone)).hour == 20


def test_wec_official_ics_times_and_cancellations():
    fuji = [s for s in _parse("fia_wec") if s.event_external_id == "6-hours-of-fuji-2026"]
    race = next(s for s in fuji if s.session_name == "Race")
    assert race.timezone == "Asia/Tokyo" and race.start_at == datetime(2026, 9, 27, 2, 0, tzinfo=UTC)
    assert race.external_id == "session-7830"  # source-provided stable id
    cancelled = {s.session_name for s in fuji if s.status.value == "cancelled"}
    assert "Qualifying - HYPERCAR" in cancelled and "Race" not in cancelled


def test_wec_utc_ics_uses_maintained_circuit_timezone():
    lm = [s for s in _parse("fia_wec") if s.event_external_id == "24-hours-of-le-mans-2026"]
    assert {s.timezone for s in lm} == {"Europe/Paris"}
    race = next(s for s in lm if s.session_name == "Race")
    assert race.start_at == datetime(2026, 6, 13, 16, 0, tzinfo=UTC)


def test_only_imsa_is_fixture_only_and_flagged_synthetic():
    assert get_source("formula1").live and get_source("fia_wec").live and get_source("gt_world_challenge").live
    imsa = get_source("imsa")
    assert not imsa.live and "synthetic" in imsa.fixture_label
    assert imsa.display_name(imsa.load_fixture()).endswith("(synthetic dev fixture)")
