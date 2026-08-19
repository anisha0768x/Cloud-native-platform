import pytest

from app.services.storage_service import validate_key
from platform_common.exceptions import ValidationError


def test_valid_key_passes():
    validate_key("reports/2026/q1.csv")  # must not raise


def test_empty_key_rejected():
    with pytest.raises(ValidationError):
        validate_key("")


def test_key_with_leading_slash_rejected():
    with pytest.raises(ValidationError):
        validate_key("/etc/passwd")


def test_key_with_path_traversal_rejected():
    with pytest.raises(ValidationError):
        validate_key("../../../etc/passwd")


def test_key_with_whitespace_rejected():
    with pytest.raises(ValidationError):
        validate_key(" reports/q1.csv ")


def test_overly_long_key_rejected():
    with pytest.raises(ValidationError):
        validate_key("a" * 2000)
