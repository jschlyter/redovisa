from redovisa.swish import get_swish_app_url


def test_get_swish_app_url():
    phone_number = "1234567890"
    amount = 42.0
    message = "Test message"
    url = get_swish_app_url(phone_number, amount, message)
    assert url == "https://app.swish.nu/1/p/sw/?sw=1234567890&amt=42.0&msg=Test+message"
