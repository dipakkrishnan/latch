import json

from .config import CONFIG_DIR

_DIR = CONFIG_DIR
_PATH = _DIR / "credentials.json"


def load():
    return json.loads(_PATH.read_text()) if _PATH.exists() else []


def save(cred: dict):
    creds = load()
    creds.append(cred)
    _save_all(creds)


def delete(credential_id: str) -> bool:
    creds = load()
    filtered = [c for c in creds if c["credentialID"] != credential_id]
    if len(filtered) == len(creds):
        return False
    _save_all(filtered)
    return True


def update_counter(credential_id: str, counter: int) -> bool:
    creds = load()
    for c in creds:
        if c["credentialID"] == credential_id:
            c["counter"] = counter
            _save_all(creds)
            return True
    return False


def _save_all(creds: list):
    _DIR.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(creds, indent=2))
