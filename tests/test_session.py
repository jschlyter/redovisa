import time

import pytest

from redovisa.session import Session, SessionHandler


@pytest.fixture
def handler():
    return SessionHandler()


@pytest.fixture
def session():
    return Session(iss="https://issuer.example", sub="user123", email="user@example.com", name="Test User")


def test_session_auto_id(session):
    other = Session(iss="https://issuer.example", sub="user123", email="user@example.com", name="Test User")
    assert session.session_id != other.session_id


def test_session_defaults(session):
    assert session.claims == {}
    assert session.expires_at is None


def test_session_cache_key():
    assert Session.get_cache_key("abc") == "session:abc"


def test_create_and_get_session(handler, session):
    expires_at = int(time.time()) + 3600
    handler.create_session(session, expires_at)
    retrieved = handler.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id
    assert retrieved.iss == session.iss
    assert retrieved.sub == session.sub
    assert retrieved.email == session.email
    assert retrieved.name == session.name


def test_get_session_not_found(handler):
    assert handler.get_session("nonexistent-id") is None


def test_delete_session(handler, session):
    expires_at = int(time.time()) + 3600
    handler.create_session(session, expires_at)
    handler.delete_session(session.session_id)
    assert handler.get_session(session.session_id) is None


def test_delete_nonexistent_session(handler):
    handler.delete_session("nonexistent-id")


def test_session_expiry_ttl_set(handler, session):
    expires_at = int(time.time()) + 3600
    handler.create_session(session, expires_at)
    ttl = handler.redis_client.ttl(Session.get_cache_key(session.session_id))
    assert ttl > 0


def test_session_with_claims(handler):
    session = Session(
        iss="https://issuer.example",
        sub="user456",
        email="user2@example.com",
        name="Another User",
        claims={"roles": ["admin"], "org": "scouts"},
    )
    expires_at = int(time.time()) + 3600
    handler.create_session(session, expires_at)
    retrieved = handler.get_session(session.session_id)
    assert retrieved.claims == {"roles": ["admin"], "org": "scouts"}
