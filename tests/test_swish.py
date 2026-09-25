from redovisa.swish import format_swish_payee, get_swish_app_url


def test_get_swish_app_url():
    phone_number = "1234567890"
    amount = 42.0
    message = "Test message with räksmörgås"
    url = get_swish_app_url(phone_number, amount, message)
    assert url == "https://app.swish.nu/1/p/sw/?sw=1234567890&amt=42.0&msg=Test+message+with+r%C3%A4ksm%C3%B6rg%C3%A5s"


def test_format_swish_payee():
    payee = "1234567890"
    formatted = format_swish_payee(payee)
    assert formatted == "1 234 567 890"
