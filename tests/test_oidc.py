from redovisa.oidc import OidcMiddleware


def test_verify_next_good():
    assert OidcMiddleware.verify_next("/next") == "/next"
    assert OidcMiddleware.verify_next("/") == "/"
    assert OidcMiddleware.verify_next("/next?foo=bar") == "/next?foo=bar"


def test_verify_next_bad():
    assert OidcMiddleware.verify_next("//next") is None
    assert OidcMiddleware.verify_next("http://example.com/next") is None
