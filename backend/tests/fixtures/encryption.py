"""Shared encryption test constants for unit and integration tests."""

from syntara.core.lib.encryption import key_from_string

# Test encryption keys (64-char hex)
OLD_KEY_HEX = "aa" * 32
NEW_KEY_HEX = "bb" * 32
WRONG_KEY_HEX = "cc" * 32
ZEROS_KEY_HEX = "00" * 32

OLD_KEY = key_from_string(OLD_KEY_HEX)
NEW_KEY = key_from_string(NEW_KEY_HEX)
WRONG_KEY = key_from_string(WRONG_KEY_HEX)
ZEROS_KEY = key_from_string(ZEROS_KEY_HEX, allow_insecure=True)
