import pyotp
from latch import totp


def test_generate_secret():
    secret = totp.generate_secret()
    assert len(secret) >= 16
    assert secret.isalnum()


def test_provisioning_uri():
    secret = totp.generate_secret()
    uri = totp.get_provisioning_uri(secret, "user@example.com", "Latch")
    assert uri.startswith("otpauth://totp/")
    assert "Latch" in uri
    assert "user%40example.com" in uri


def test_verify_valid_code():
    secret = totp.generate_secret()
    code = pyotp.TOTP(secret).now()
    assert totp.verify(code, secret=secret) is True


def test_verify_invalid_code():
    secret = totp.generate_secret()
    assert totp.verify("000000", secret=secret) is False


def test_verify_no_secret():
    assert totp.verify("123456", secret=None) is False


def test_verify_strips_whitespace():
    secret = totp.generate_secret()
    code = pyotp.TOTP(secret).now()
    assert totp.verify(f"  {code}  ", secret=secret) is True
