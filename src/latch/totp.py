import pyotp

from .config import load_totp_secret, save_totp_secret


def generate_secret() -> str:
    return pyotp.random_base32()


def get_provisioning_uri(secret: str, account: str, issuer: str = "Latch") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def verify(code: str, secret: str | None = None) -> bool:
    s = secret or load_totp_secret()
    if not s:
        return False
    # valid_window=1 allows ±30s clock drift
    return pyotp.TOTP(s).verify(code.strip(), valid_window=1)


def is_enrolled() -> bool:
    return load_totp_secret() is not None


def enroll(secret: str) -> None:
    save_totp_secret(secret)
