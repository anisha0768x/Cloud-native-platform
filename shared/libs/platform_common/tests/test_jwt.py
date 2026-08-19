import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from platform_common.exceptions import UnauthorizedError
from platform_common.security.jwt import decode_and_verify, encode_token


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def test_encode_and_verify_roundtrip(rsa_keypair):
    private_key, public_key = rsa_keypair
    token = encode_token(
        private_key=private_key,
        subject="user-123",
        roles=["admin"],
        permissions=["service:create"],
        expires_in_seconds=3600,
    )
    payload = decode_and_verify(token, public_key=public_key)
    assert payload.sub == "user-123"
    assert "service:create" in payload.permissions


def test_verify_rejects_tampered_token(rsa_keypair):
    _, public_key = rsa_keypair
    with pytest.raises(UnauthorizedError):
        decode_and_verify("not.a.validtoken", public_key=public_key)
