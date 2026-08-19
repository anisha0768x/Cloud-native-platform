"""
Generates the RS256 keypair used for local development.

In staging/prod, this keypair is generated once and stored in a secrets
manager / K8s Secret — this script is for local dev convenience only, so
a fresh clone of the repo can get a working keypair in one command instead
of the developer needing to know openssl incantations.

Usage: python scripts/generate_keys.py
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

OUT_DIR = Path(__file__).parent.parent / "keys"


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    (OUT_DIR / "private_key.pem").write_bytes(private_pem)
    (OUT_DIR / "public_key.pem").write_bytes(public_pem)

    print(f"Keys written to {OUT_DIR}/")
    print("Copy public_key.pem's contents to every OTHER service's JWT_PUBLIC_KEY env var.")
    print("private_key.pem stays in auth-service ONLY — never copy it elsewhere.")


if __name__ == "__main__":
    main()
