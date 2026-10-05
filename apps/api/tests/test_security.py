import hashlib
import logging

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.config import Settings, get_settings
from app.models import CalendarFeed
from app.ratelimit import SlidingWindowLimiter

BODY = {"series": ["formula-1"], "session_types": ["race"], "timezone": "UTC"}


@pytest.fixture
def feed(client, series):
    return client.post("/feeds", json=BODY).json()


def test_tokens_are_random_and_edit_token_is_only_stored_hashed(client, db, series):
    feeds = [client.post("/feeds", json=BODY).json() for _ in range(5)]
    assert len({f["public_token"] for f in feeds}) == 5 and len({f["edit_token"] for f in feeds}) == 5
    assert all(len(f["public_token"]) == 10 and len(f["edit_token"]) >= 32 for f in feeds)
    row = db.scalar(select(CalendarFeed).where(CalendarFeed.public_token == feeds[0]["public_token"]))
    assert row.edit_token_hash == hashlib.sha256(feeds[0]["edit_token"].encode()).hexdigest()
    assert feeds[0]["edit_token"] not in str(row.__dict__)
    assert feeds[0]["edit_token"] not in feeds[0]["public_url"] and feeds[0]["edit_token"] not in feeds[0]["webcal_url"]


def test_public_token_grants_no_edit_capability(client, feed):
    tok = feed["public_token"]
    for headers in ({}, {"X-Edit-Token": tok}):  # the public token is not an edit token either
        assert client.patch(f"/feeds/{tok}", json={"timezone": "Asia/Tokyo"}, headers=headers).status_code == 403
        assert client.delete(f"/feeds/{tok}", headers=headers).status_code == 403
    assert client.get(f"/feeds/{tok}").status_code == 200  # reading what the .ics already reveals


def test_edit_token_of_another_feed_is_rejected(client, series):
    a, b = client.post("/feeds", json=BODY).json(), client.post("/feeds", json=BODY).json()
    r = client.patch(f"/feeds/{a['public_token']}", json={"timezone": "UTC"}, headers={"X-Edit-Token": b["edit_token"]})
    assert r.status_code == 403


def test_revoked_feed_returns_410_everywhere(client, feed):
    h = {"X-Edit-Token": feed["edit_token"]}
    assert client.delete(f"/feeds/{feed['public_token']}", headers=h).status_code == 204
    for path in (f"/calendar/{feed['public_token']}.ics", f"/feeds/{feed['public_token']}",
                 f"/feeds/{feed['public_token']}/changes"):
        assert client.get(path).status_code == 410
    assert client.patch(f"/feeds/{feed['public_token']}", json={"timezone": "UTC"}, headers=h).status_code == 410


def test_mutations_are_rate_limited(client, series, monkeypatch):
    monkeypatch.setattr(get_settings(), "feed_rate_limit_per_minute", 3)
    codes = [client.post("/feeds", json=BODY).status_code for _ in range(5)]
    assert codes == [201, 201, 201, 429, 429]
    r = client.post("/feeds", json=BODY)
    assert int(r.headers["retry-after"]) >= 1
    assert client.get("/series").status_code == 200  # reads are not limited


def test_sliding_window_frees_slots():
    lim = SlidingWindowLimiter()
    assert [lim.check("ip", 2, 60, now=t) for t in (0, 1)] == [None, None]
    assert lim.check("ip", 2, 60, now=2) == pytest.approx(58)
    assert lim.check("ip", 2, 60, now=61) is None
    assert lim.check("other", 2, 60, now=2) is None


def test_forwarded_for_only_trusted_when_configured(client, series, monkeypatch):
    monkeypatch.setattr(get_settings(), "feed_rate_limit_per_minute", 1)
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    assert client.post("/feeds", json=BODY, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 201
    assert client.post("/feeds", json=BODY, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 201
    assert client.post("/feeds", json=BODY, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429


def test_edit_token_in_query_string_is_not_accepted(client, feed):
    r = client.patch(f"/feeds/{feed['public_token']}?token={feed['edit_token']}", json={"timezone": "Asia/Tokyo"})
    assert r.status_code == 403


def test_no_secrets_in_logs(client, feed, caplog):
    secret = feed["edit_token"]
    with caplog.at_level(logging.DEBUG):
        client.patch(f"/feeds/{feed['public_token']}", json={"timezone": "Asia/Tokyo"}, headers={"X-Edit-Token": secret})
        client.get(f"/manage-probe?token={secret}")
    dump = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert secret not in dump
    access = [r for r in caplog.records if r.name == "gridline.access"]
    assert access and all("token" not in r.path for r in access)


def test_cors_is_restricted(client):
    ok = client.options("/feeds", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options("/feeds", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers
    assert "PUT" not in ok.headers["access-control-allow-methods"]


def test_production_config_rejects_wildcard_cors_and_localhost_base_url():
    db = "postgresql+psycopg://u:p@ep.neon.tech/gridline"
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(environment="production", database_url=db, cors_origins="*", public_api_base_url="https://api.example.com")
    with pytest.raises(ValidationError, match="PUBLIC_API_BASE_URL"):
        Settings(environment="production", database_url=db, cors_origins="https://example.com")
    Settings(environment="production", database_url=db, cors_origins="https://example.com", public_api_base_url="https://api.example.com")


def test_a_forged_left_most_forwarded_for_entry_does_not_dodge_the_limit(client, series, monkeypatch):
    """The proxy appends the real client as the LAST entry; anything before it is attacker-controlled."""
    monkeypatch.setattr(get_settings(), "feed_rate_limit_per_minute", 1)
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    first = client.post("/feeds", json=BODY, headers={"X-Forwarded-For": "9.9.9.1, 3.3.3.3"})
    spoof = client.post("/feeds", json=BODY, headers={"X-Forwarded-For": "9.9.9.2, 3.3.3.3"})
    assert first.status_code == 201 and spoof.status_code == 429


def test_garbage_forwarded_for_values_are_not_used_as_keys(client, series, monkeypatch):
    monkeypatch.setattr(get_settings(), "feed_rate_limit_per_minute", 1)
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    assert client.post("/feeds", json=BODY, headers={"X-Forwarded-For": "not-an-ip-1"}).status_code == 201
    assert client.post("/feeds", json=BODY, headers={"X-Forwarded-For": "not-an-ip-2"}).status_code == 429  # same real peer
