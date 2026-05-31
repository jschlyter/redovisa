import pytest
from fastapi import HTTPException

from redovisa.oidc.state import StateHandler


@pytest.fixture
def handler():
    return StateHandler()


def test_init_no_secret():
    h = StateHandler()
    assert h.state_key is not None


def test_init_with_secret():
    h = StateHandler(secret="testsecretthatis32byteslong12345")
    assert h.state_key is not None


def test_encode_returns_string(handler):
    token = handler.encode({"nonce": "abc", "next": "/home"})
    assert isinstance(token, str)
    assert len(token) > 0


def test_encode_decode_roundtrip(handler):
    payload = {"nonce": "xyz", "next": "/dashboard"}
    token = handler.encode(payload)
    decoded = handler.decode(token)
    assert decoded == payload


def test_encode_decode_empty_payload(handler):
    token = handler.encode({})
    assert handler.decode(token) == {}


def test_encode_decode_nested_payload(handler):
    payload = {"nonce": "abc", "extra": {"foo": [1, 2, 3]}}
    assert handler.decode(handler.encode(payload)) == payload


def test_same_secret_cross_instance_decode():
    secret = "sharedsecretthatisatleast32bytes!"
    h1 = StateHandler(secret=secret)
    h2 = StateHandler(secret=secret)
    token = h1.encode({"nonce": "n1"})
    assert h2.decode(token) == {"nonce": "n1"}


def test_different_secret_cannot_decode():
    h1 = StateHandler(secret="firstsecretthatisatleast32bytes!")
    h2 = StateHandler(secret="secondsecretthatisatleast32bytes")
    token = h1.encode({"nonce": "n1"})
    with pytest.raises(HTTPException) as exc_info:
        h2.decode(token)
    assert exc_info.value.status_code == 400


def test_decode_invalid_token_raises(handler):
    with pytest.raises(HTTPException) as exc_info:
        handler.decode("not.a.valid.jwe.token")
    assert exc_info.value.status_code == 400
    assert "state" in exc_info.value.detail.lower()


def test_decode_tampered_token_raises(handler):
    token = handler.encode({"nonce": "abc"})
    tampered = token[:-10] + "AAAAAAAAAA"
    with pytest.raises(HTTPException) as exc_info:
        handler.decode(tampered)
    assert exc_info.value.status_code == 400


def test_decode_empty_string_raises(handler):
    with pytest.raises(HTTPException) as exc_info:
        handler.decode("")
    assert exc_info.value.status_code == 400


def test_encode_produces_different_tokens_each_call(handler):
    payload = {"nonce": "abc"}
    assert handler.encode(payload) != handler.encode(payload)
