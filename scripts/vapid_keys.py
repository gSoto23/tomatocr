"""Makes the key pair for phone notifications (web push), once per server. Prints the two
lines to add to .env; then restart `tomato`. docs/NOTIFICACIONES.md.

    PYTHONPATH=. .venv/bin/python scripts/vapid_keys.py

Changing them later makes every phone turn notifications on again: keep them.
"""
import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def main():
    vapid = Vapid()
    vapid.generate_keys()
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    print(f"VAPID_PUBLIC_KEY={b64(public)}")
    print(f"VAPID_PRIVATE_KEY={b64(private)}")


if __name__ == "__main__":
    main()
