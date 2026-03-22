from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    public_key_b64: str
    _private_key: Ed25519PrivateKey

    def sign(self, data: str) -> str:
        sig = self._private_key.sign(data.encode("utf-8"))
        return base64.b64encode(sig).decode("ascii")

    def sign_connect(
        self, *, client_id: str, client_mode: str, role: str,
        scopes: list[str], signed_at_ms: int, token: str, nonce: str,
    ) -> str:
        """Sign v2 pipe-delimited connect payload per Gateway protocol."""
        payload = "|".join([
            "v2", self.device_id, client_id, client_mode, role,
            ",".join(scopes), str(signed_at_ms), token, nonce,
        ])
        return self.sign(payload)


def load_or_create_identity(path: str) -> DeviceIdentity:
    key_path = Path(path).expanduser()
    key_path.parent.mkdir(parents=True, exist_ok=True)

    if key_path.exists():
        private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise RuntimeError(f"Unsupported key type in {key_path}")
    else:
        private_key = Ed25519PrivateKey.generate()
        key_path.write_bytes(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        os.chmod(key_path, 0o600)

    pub = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    return DeviceIdentity(
        device_id=hashlib.sha256(pub).hexdigest(),
        public_key_b64=base64.b64encode(pub).decode("ascii"),
        _private_key=private_key,
    )
