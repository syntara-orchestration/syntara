"""Unit tests for audit event sanitization utilities."""

# mypy: disable-error-code="attr-defined"

from typing import Any

from pydantic import BaseModel

from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.sanitization import (
    REDACTED,
    EventSanitizer,
    PIIDetector,
    redact_by_camel_case_key,
    redact_by_partial_key,
    redact_email,
)
from syntara.audit.sanitization import (
    sanitizer as default_sanitizer,
)


class TestRedactByKey:
    """Test the redact_by_partial_key detector function."""

    def test_redacts_exact_matches(self) -> None:
        """Test that exact matches are redacted."""
        detector = redact_by_partial_key(["password", "secret", "token"])

        assert detector("sensitive_data", "password") == REDACTED
        assert detector("sensitive_data", "secret") == REDACTED
        assert detector("sensitive_data", "token") == REDACTED

    def test_redacts_underscore_prefixed_patterns(self) -> None:
        """Test that underscore-prefixed patterns are redacted."""
        detector = redact_by_partial_key(["password", "secret", "token"])

        assert detector("sensitive_data", "_password") == REDACTED
        assert detector("sensitive_data", "_secret") == REDACTED
        assert detector("sensitive_data", "_token") == REDACTED

    def test_redacts_underscore_suffixed_patterns(self) -> None:
        """Test that underscore-suffixed patterns are redacted."""
        detector = redact_by_partial_key(["password", "secret", "token"])

        assert detector("sensitive_data", "password_") == REDACTED
        assert detector("sensitive_data", "secret_") == REDACTED
        assert detector("sensitive_data", "token_") == REDACTED

    def test_redacts_underscore_bounded_patterns(self) -> None:
        """Test that underscore-bounded patterns are redacted."""
        detector = redact_by_partial_key(["password", "secret", "token"])

        assert detector("sensitive_data", "user_password_hash") == REDACTED
        assert detector("sensitive_data", "api_secret_key") == REDACTED
        assert detector("sensitive_data", "auth_token_store") == REDACTED

    def test_redacts_variations_with_underscores(self) -> None:
        """Test that various underscore patterns are redacted."""
        detector = redact_by_partial_key(["password", "key", "auth"])

        # Prefix variations
        assert detector("sensitive", "user_password") == REDACTED
        assert detector("sensitive", "admin_password") == REDACTED
        assert detector("sensitive", "api_key") == REDACTED
        assert detector("sensitive", "encryption_key") == REDACTED
        assert detector("sensitive", "basic_auth") == REDACTED

        # Suffix variations
        assert detector("sensitive", "password_hash") == REDACTED
        assert detector("sensitive", "password_store") == REDACTED
        assert detector("sensitive", "key_") == REDACTED
        assert detector("sensitive", "auth_") == REDACTED

        # Both prefix and suffix
        assert detector("sensitive", "_password_") == REDACTED
        assert detector("sensitive", "_key_store") == REDACTED
        assert detector("sensitive", "user_auth_token") == REDACTED

    def test_case_insensitive_matching(self) -> None:
        """Test that matching is case insensitive."""
        detector = redact_by_partial_key(["password", "secret"])

        assert detector("sensitive", "PASSWORD") == REDACTED
        assert detector("sensitive", "Password") == REDACTED
        assert detector("sensitive", "user_PASSWORD") == REDACTED
        assert detector("sensitive", "API_SECRET") == REDACTED
        assert detector("sensitive", "_Secret_") == REDACTED

    def test_ignores_patterns_within_words(self) -> None:
        """Test that patterns within words (no underscore boundaries) are not matched."""
        detector = redact_by_partial_key(["key", "auth", "pass"])

        # These should NOT match - pattern within word without underscore boundaries
        assert detector("data", "keyboard") is None  # "key" in "keyboard"
        assert detector("data", "monkey") is None  # "key" in "monkey"
        assert detector("data", "author") is None  # "auth" in "author"
        assert detector("data", "authentic") is None  # "auth" in "authentic"
        assert detector("data", "passage") is None  # "pass" in "passage"
        assert detector("data", "compass") is None  # "pass" in "compass"

    def test_ignores_non_matching_keys(self) -> None:
        """Test that non-matching keys are not redacted."""
        detector = redact_by_partial_key(["password", "secret"])

        assert detector("some_data", "username") is None
        assert detector("some_data", "email") is None
        assert detector("some_data", "normal_field") is None
        assert detector("some_data", "config_setting") is None

    def test_prevents_bypass_attacks(self) -> None:
        """Test that this detector prevents common bypass attempts."""
        detector = redact_by_partial_key(["password", "secret", "token", "key"])

        # Common bypass variations that would evade exact matching
        assert detector("sensitive", "user_password") == REDACTED
        assert detector("sensitive", "api_secret") == REDACTED
        assert detector("sensitive", "auth_token") == REDACTED
        assert detector("sensitive", "encryption_key") == REDACTED
        assert detector("sensitive", "client_secret") == REDACTED
        assert detector("sensitive", "access_token") == REDACTED
        assert detector("sensitive", "private_key") == REDACTED
        assert detector("sensitive", "session_secret") == REDACTED

    def test_empty_patterns(self) -> None:
        """Test behavior with empty patterns list."""
        detector = redact_by_partial_key([])

        assert detector("some_data", "password") is None
        assert detector("some_data", "user_password") is None


class TestRedactByKeyKebabCaseAndDotNotation:
    """Test redact_by_partial_key with kebab-case and dot-notation support."""

    def test_redacts_kebab_case_patterns(self) -> None:
        """Test that kebab-case patterns are redacted."""
        detector = redact_by_partial_key(["password", "secret", "token"])

        assert detector("sensitive_data", "api-password") == REDACTED
        assert detector("sensitive_data", "client-secret") == REDACTED
        assert detector("sensitive_data", "auth-token") == REDACTED
        assert detector("sensitive_data", "user-password-hash") == REDACTED

    def test_redacts_dot_notation_patterns(self) -> None:
        """Test that dot-notation patterns are redacted."""
        detector = redact_by_partial_key(["password", "secret", "token"])

        assert detector("sensitive_data", "config.password") == REDACTED
        assert detector("sensitive_data", "db.secret") == REDACTED
        assert detector("sensitive_data", "session.token") == REDACTED
        assert detector("sensitive_data", "auth.password.hash") == REDACTED

    def test_redacts_mixed_delimiter_patterns(self) -> None:
        """Test that mixed delimiter patterns are redacted."""
        detector = redact_by_partial_key(["password", "secret", "key"])

        # Mix of underscores, hyphens, and dots
        assert detector("sensitive", "user_password") == REDACTED
        assert detector("sensitive", "api-secret") == REDACTED
        assert detector("sensitive", "config.key") == REDACTED
        assert detector("sensitive", "db-password") == REDACTED
        assert detector("sensitive", "auth.secret") == REDACTED

    def test_handles_multiple_delimiters_in_same_key(self) -> None:
        """Test keys with multiple different delimiters."""
        detector = redact_by_partial_key(["password", "secret"])

        assert detector("sensitive", "user_api-password") == REDACTED
        assert detector("sensitive", "config.db_secret") == REDACTED
        assert detector("sensitive", "auth-service.password") == REDACTED

    def test_ignores_kebab_case_non_matches(self) -> None:
        """Test that non-matching kebab-case keys are not redacted."""
        detector = redact_by_partial_key(["password", "secret"])

        assert detector("data", "user-name") is None
        assert detector("data", "api-endpoint") is None
        assert detector("data", "auth-header") is None

    def test_ignores_dot_notation_non_matches(self) -> None:
        """Test that non-matching dot-notation keys are not redacted."""
        detector = redact_by_partial_key(["password", "secret"])

        assert detector("data", "config.debug") is None
        assert detector("data", "db.host") is None
        assert detector("data", "service.name") is None


class TestRedactByCamelCaseKey:
    """Test the redact_by_camel_case_key detector function."""

    def test_redacts_camel_case_patterns(self) -> None:
        """Test that camelCase patterns are redacted."""
        detector = redact_by_camel_case_key(["password", "secret", "token"])

        assert detector("sensitive_data", "userPassword") == REDACTED
        assert detector("sensitive_data", "apiSecret") == REDACTED
        assert detector("sensitive_data", "authToken") == REDACTED
        assert detector("sensitive_data", "clientSecret") == REDACTED
        assert detector("sensitive_data", "accessToken") == REDACTED

    def test_redacts_pascal_case_patterns(self) -> None:
        """Test that PascalCase patterns are redacted."""
        detector = redact_by_camel_case_key(["password", "secret", "token"])

        assert detector("sensitive_data", "UserPassword") == REDACTED
        assert detector("sensitive_data", "ApiSecret") == REDACTED
        assert detector("sensitive_data", "AuthToken") == REDACTED

    def test_redacts_multi_word_camel_case(self) -> None:
        """Test that multi-word camelCase patterns are redacted."""
        detector = redact_by_camel_case_key(["password", "secret", "key"])

        assert detector("sensitive", "userPasswordHash") == REDACTED
        assert detector("sensitive", "apiSecretKey") == REDACTED
        assert detector("sensitive", "encryptionKeyValue") == REDACTED
        assert detector("sensitive", "adminPasswordReset") == REDACTED

    def test_matches_pattern_anywhere_in_camel_case(self) -> None:
        """Test that pattern matches anywhere in the camelCase key."""
        detector = redact_by_camel_case_key(["password", "token", "auth"])

        # Pattern at start
        assert detector("sensitive", "passwordHash") == REDACTED
        assert detector("sensitive", "tokenValue") == REDACTED

        # Pattern in middle
        assert detector("sensitive", "userPasswordHash") == REDACTED
        assert detector("sensitive", "apiTokenStore") == REDACTED

        # Pattern at end
        assert detector("sensitive", "userPassword") == REDACTED
        assert detector("sensitive", "bearerToken") == REDACTED
        assert detector("sensitive", "basicAuth") == REDACTED

    def test_case_insensitive_matching(self) -> None:
        """Test that camelCase matching is case insensitive."""
        detector = redact_by_camel_case_key(["password", "secret"])

        assert detector("sensitive", "userPassword") == REDACTED
        assert detector("sensitive", "userPASSWORD") == REDACTED
        assert detector("sensitive", "apiSecret") == REDACTED
        assert detector("sensitive", "apiSECRET") == REDACTED

    def test_ignores_non_matching_camel_case_keys(self) -> None:
        """Test that non-matching camelCase keys are not redacted."""
        detector = redact_by_camel_case_key(["password", "secret"])

        assert detector("data", "userName") is None
        assert detector("data", "userId") is None
        assert detector("data", "apiEndpoint") is None
        assert detector("data", "configValue") is None

    def test_does_not_match_partial_words(self) -> None:
        """Test that patterns don't match as substrings within camelCase words."""
        detector = redact_by_camel_case_key(["pass", "key", "auth"])

        # "pass" should not match "Passport", "key" should not match "Keyboard", etc.
        assert detector("data", "userPassport") is None
        assert detector("data", "keyboardLayout") is None
        assert detector("data", "authorName") is None

    def test_handles_single_word_keys(self) -> None:
        """Test that single-word keys (no camelCase) are handled correctly."""
        detector = redact_by_camel_case_key(["password", "secret"])

        # Exact match (all lowercase)
        assert detector("sensitive", "password") == REDACTED
        assert detector("sensitive", "secret") == REDACTED

        # Non-match
        assert detector("data", "username") is None
        assert detector("data", "config") is None

    def test_real_world_oidc_patterns(self) -> None:
        """Test real-world OIDC/OAuth camelCase patterns."""
        detector = redact_by_camel_case_key(["secret", "token", "key"])

        # Common OIDC/OAuth field names
        assert detector("sensitive", "clientSecret") == REDACTED
        assert detector("sensitive", "accessToken") == REDACTED
        assert detector("sensitive", "refreshToken") == REDACTED
        assert detector("sensitive", "idToken") == REDACTED
        assert detector("sensitive", "apiKey") == REDACTED

    def test_real_world_llm_api_patterns(self) -> None:
        """Test real-world LLM API response patterns."""
        detector = redact_by_camel_case_key(["key", "token", "auth"])

        # Common LLM API field names (OpenAI, Anthropic conventions)
        assert detector("sensitive", "apiKey") == REDACTED
        assert detector("sensitive", "authToken") == REDACTED
        assert detector("sensitive", "accessKey") == REDACTED

    def test_empty_key_handling(self) -> None:
        """Test handling of empty keys."""
        detector = redact_by_camel_case_key(["password"])

        assert detector("value", "") is None

    def test_all_uppercase_key(self) -> None:
        """Test handling of all-uppercase keys (no camelCase)."""
        detector = redact_by_camel_case_key(["password"])

        # All uppercase should be treated as single word
        assert detector("value", "PASSWORD") == REDACTED
        assert detector("value", "SECRET") is None  # Pattern not in list


class TestRedactEmail:
    """Test the redact_email detector function."""

    def test_redacts_valid_emails(self) -> None:
        """Test that valid email addresses are redacted."""
        assert redact_email("user@example.com", "email") == "[EMAIL_REDACTED]"
        assert redact_email("test.user@company.co.uk", "user_email") == "[EMAIL_REDACTED]"
        assert redact_email("admin@test.org", "contact") == "[EMAIL_REDACTED]"
        assert redact_email("john.doe+newsletter@subdomain.example.com", "email") == "[EMAIL_REDACTED]"
        assert redact_email("user123@localhost.localdomain", "email") == "[EMAIL_REDACTED]"

    def test_ignores_non_email_strings(self) -> None:
        """Test that non-email strings are not redacted."""
        assert redact_email("not_an_email", "email") is None
        assert redact_email("missing@domain", "email") is None
        assert redact_email("user@", "email") is None
        assert redact_email("@domain.com", "email") is None
        assert redact_email("user.name", "email") is None

        # These were false positives in the original simple implementation
        assert redact_email("see RFC 2822 @ section 3.4.1", "text") is None
        assert redact_email("config@v2.0", "version") is None  # No TLD
        assert redact_email("config@v2.0.1", "version") is None  # Numeric TLD (not email)
        assert redact_email("user@host", "config") is None  # No TLD
        assert redact_email("@domain.com", "text") is None  # No local part
        assert redact_email("user@", "text") is None  # No domain

    def test_intentional_over_matching_for_security(self) -> None:
        """Test cases where we intentionally over-match for security (documented behavior)."""
        # These may look like false positives but are intentionally caught for security
        assert redact_email("user@localhost.local", "config") == "[EMAIL_REDACTED]"  # Local email
        assert redact_email("user@service.internal", "config") == "[EMAIL_REDACTED]"  # Internal service email

    def test_email_detection_in_longer_strings(self) -> None:
        """Test email detection within longer text strings."""
        assert redact_email("Contact me at john@example.com for details", "message") == "[EMAIL_REDACTED]"
        assert redact_email("Email: admin@test.org, Phone: 123-456", "contact_info") == "[EMAIL_REDACTED]"
        assert redact_email("Send logs to support@company.co.uk", "instruction") == "[EMAIL_REDACTED]"

    def test_ignores_non_string_values(self) -> None:
        """Test that non-string values are not redacted."""
        assert redact_email(123, "email") is None
        assert redact_email(None, "email") is None
        assert redact_email(["user@example.com"], "email") is None
        assert redact_email({"email": "user@example.com"}, "email") is None

    def test_ignores_key_parameter(self) -> None:
        """Test that the key parameter is ignored (function signature requirement)."""
        assert redact_email("user@example.com", "not_email_key") == "[EMAIL_REDACTED]"
        assert redact_email("user@example.com", "") == "[EMAIL_REDACTED]"


class TestEventSanitizer:
    """Test the EventSanitizer class."""

    def test_initialization_with_defaults(self) -> None:
        """Test sanitizer initialization with default values."""
        sanitizer = EventSanitizer()

        assert sanitizer.detectors == []
        assert sanitizer.max_depth == 10

    def test_initialization_with_custom_values(self) -> None:
        """Test sanitizer initialization with custom values."""
        detectors: list[PIIDetector] = [redact_email, redact_by_partial_key(["secret"])]
        sanitizer = EventSanitizer(detectors=detectors, max_depth=5)

        assert sanitizer.detectors == detectors
        assert sanitizer.max_depth == 5

    def test_sanitize_primitives(self) -> None:
        """Test sanitization of primitive values."""
        detector = redact_by_partial_key(["secret"])
        sanitizer = EventSanitizer(detectors=[detector])

        # Should apply detectors to primitives (exact match and partial)
        assert sanitizer._apply_detectors("value", "secret") == REDACTED
        assert sanitizer._apply_detectors("value", "normal_key") == "value"
        assert sanitizer._apply_detectors(123, "secret") == REDACTED
        assert sanitizer._apply_detectors(None, "secret") == REDACTED

    def test_sanitize_audit_data_base(self) -> None:
        """Test sanitization of AuditContextData objects."""
        sanitizer = EventSanitizer(detectors=[redact_by_partial_key(["password"]), redact_email])

        data = AuditContextData(data_type="test", error_type="ValidationError", error_message="john@example.com")

        sanitized_data = sanitizer.sanitize(data)
        assert sanitized_data.error_type == "ValidationError"
        assert sanitized_data.error_message == "[EMAIL_REDACTED]"

    def test_sanitize_audit_context_data_with_extras(self) -> None:
        """Test sanitization of AuditContextData with model_extra fields."""
        sanitizer = EventSanitizer(detectors=[redact_by_partial_key(["password"]), redact_email])

        data = AuditContextData(data_type="test", error_message="admin@example.com")
        # Add extra fields (model_extra) using setattr since model has extra="allow"
        data.password_field = "secret123"  # noqa: S105
        data.email_field = "user@domain.com"
        data.normal_field = "normal_data"

        sanitized_data = sanitizer.sanitize(data)
        assert sanitized_data.error_message == "[EMAIL_REDACTED]"
        # Extra fields should be sanitized too
        assert sanitized_data.password_field == REDACTED
        assert sanitized_data.email_field == "[EMAIL_REDACTED]"
        assert sanitized_data.normal_field == "normal_data"

    def test_sanitize_audit_data_function(self) -> None:
        """Test sanitization of AuditContextData with nested structures."""
        sanitizer = EventSanitizer(detectors=[redact_by_partial_key(["secret"])])

        data = AuditContextData(
            data_type="test",
            function_args={"user": {"name": "John", "credentials": {"secret_key": "sensitive_data"}}},
            function_result={"parameters": {"debug": True}},
        )

        sanitized_data = sanitizer.sanitize(data)
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["user"]["name"] == "John"
        assert sanitized_data.function_args["user"]["credentials"]["secret_key"] == REDACTED
        assert sanitized_data.function_result is not None
        assert sanitized_data.function_result["parameters"]["debug"] is True

    def test_sanitize_audit_data_with_lists(self) -> None:
        """Test sanitization of audit data with list structures."""
        sanitizer = EventSanitizer(detectors=[redact_email])

        data = AuditContextData(
            data_type="test",
            function_args={"emails": ["john@example.com", "not_an_email", "jane@test.org"]},
            function_result={"numbers": [1, 2, 3]},
        )

        sanitized_data = sanitizer.sanitize(data)

        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["emails"] == ["[EMAIL_REDACTED]", "not_an_email", "[EMAIL_REDACTED]"]
        assert sanitized_data.function_result is not None
        assert sanitized_data.function_result["numbers"] == [1, 2, 3]

    def test_circular_reference_detection_audit_data(self) -> None:
        """Test handling of circular references in audit data."""
        sanitizer = EventSanitizer()

        circular_dict: dict[str, Any] = {"key": "value"}
        circular_dict["self"] = circular_dict  # Create circular reference

        data = AuditContextData(data_type="test", function_args={"data": circular_dict})

        sanitized_data = sanitizer.sanitize(data)

        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["data"]["key"] == "value"
        assert sanitized_data.function_args["data"]["self"] == "[CIRCULAR]"

    def test_max_depth_limit_audit_data(self) -> None:
        """Test max depth limit enforcement with audit data."""
        sanitizer = EventSanitizer(max_depth=2)

        # Create nested structure deeper than max_depth
        # max_depth=2 allows 2 container objects (root dict + level1 dict),
        # then truncates at level2's value
        nested_data = {"level1": {"level2": {"level3": {"level4": "deep_value"}}}}
        data = AuditContextData(data_type="test", function_args=nested_data)

        sanitized_data = sanitizer.sanitize(data)

        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["level1"]["level2"] == "[MAX_DEPTH]"

    def test_pydantic_model_handling_in_audit_data(self) -> None:
        """Test handling of nested Pydantic models in audit data."""

        class TestModel(BaseModel):
            username: str
            password: str
            email: str

        model = TestModel(username="john", password="secret", email="john@example.com")  # noqa: S106
        sanitizer = EventSanitizer(detectors=[redact_by_partial_key(["password"]), redact_email])

        data = AuditContextData(data_type="test", function_args={"user_data": model})

        sanitized_data = sanitizer.sanitize(data)

        # The nested Pydantic model should be converted to dict and sanitized
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        user_data = sanitized_data.function_args["user_data"]
        assert user_data["username"] == "john"
        assert user_data["password"] == REDACTED
        assert user_data["email"] == "[EMAIL_REDACTED]"

    def test_bytes_handling_in_audit_data(self) -> None:
        """Test handling of bytes and bytearray objects in audit data."""
        sanitizer = EventSanitizer()

        data = AuditContextData(
            data_type="test",
            function_args={"binary_data": b"hello world"},
            function_result={"byte_array": bytearray(b"test data")},
        )

        sanitized_data = sanitizer.sanitize(data)

        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["binary_data"] == "hello world"
        assert sanitized_data.function_result is not None
        assert sanitized_data.function_result["byte_array"] == "test data"

    def test_bytes_with_invalid_utf8_in_audit_data(self) -> None:
        """Test handling of bytes with invalid UTF-8 in audit data."""
        sanitizer = EventSanitizer()

        data = AuditContextData(data_type="test", function_args={"invalid_utf8": b"\xff\xfe"})

        sanitized_data = sanitizer.sanitize(data)

        # Should handle invalid UTF-8 gracefully
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert isinstance(sanitized_data.function_args["invalid_utf8"], str)

    def test_fallback_string_conversion_in_audit_data(self) -> None:
        """Test fallback string conversion for unknown types in audit data."""

        class CustomObject:
            def __str__(self) -> str:
                return "custom_object_string"

        sanitizer = EventSanitizer()
        data = AuditContextData(data_type="test", function_args={"custom": CustomObject()})

        sanitized_data = sanitizer.sanitize(data)
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["custom"] == "custom_object_string"

    def test_multiple_detectors(self) -> None:
        """Test that multiple detectors are applied in order."""

        def first_detector(_value: object, key: str) -> str | None:
            if key == "special":
                return "[FIRST_DETECTOR]"
            return None

        def second_detector(_value: object, key: str) -> str | None:
            if key == "special":
                return "[SECOND_DETECTOR]"  # Should not be reached
            return None

        sanitizer = EventSanitizer(detectors=[first_detector, second_detector])

        data = AuditContextData(data_type="test", function_args={"special": "value"})

        sanitized_data = sanitizer.sanitize(data)
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        result = sanitized_data.function_args["special"]

        # First detector should take precedence
        assert result == "[FIRST_DETECTOR]"

    def test_no_detectors_audit_data(self) -> None:
        """Test sanitization with no detectors configured on audit data."""
        sanitizer = EventSanitizer(detectors=[])

        original_args = {"password": "secret", "email": "user@example.com", "normal": "data"}
        data = AuditContextData(data_type="test", function_args=original_args.copy())

        sanitized_data = sanitizer.sanitize(data)

        # Nothing should be redacted
        assert sanitized_data.function_args is not None
        assert sanitized_data.function_args == original_args

    def test_crud_nested_password_hash_changes_are_redacted(self) -> None:
        """AAP-83644: CRUD diffs keep {old,new} shape but redact nested secret values.

        Uses the real trigger payload shape: data_type=crud_operation with top-level
        changes (see audit trigger jsonb_build_object / outbox worker sanitize path).
        """
        data = AuditContextData(
            data_type="crud_operation",
            operation="update",
            model_name="User",
            changes={
                "password_hash": {
                    "old": "$argon2id$v=19$m=65536,t=3,p=4$oldhash",
                    "new": "$argon2id$v=19$m=65536,t=3,p=4$newhash",
                },
                "username": "alice",
            },
        )

        sanitized_data = default_sanitizer.sanitize(data)

        changes = sanitized_data.changes
        # Preserve DB-trigger changeset shape; redact leaf values via parent key.
        assert changes["password_hash"] == {"old": REDACTED, "new": REDACTED}
        assert changes["username"] == "alice"
        assert "$argon2id$" not in str(changes)

    def test_crud_nested_secret_id_changes_are_redacted(self) -> None:
        """AAP-83644: same nesting leak for identityprovider.secret_id diffs."""
        data = AuditContextData(
            data_type="crud_operation",
            operation="update",
            model_name="IdentityProvider",
            changes={
                "secret_id": {
                    "old": "old-secret-uuid",
                    "new": "new-secret-uuid",
                }
            },
        )

        sanitized_data = default_sanitizer.sanitize(data)

        assert sanitized_data.changes["secret_id"] == {
            "old": REDACTED,
            "new": REDACTED,
        }

    def test_non_crud_nested_fields_are_not_redacted_via_parent_key(self) -> None:
        """Parent credential-like keys must not redact unrelated nested fields.

        Only mapping children named old/new inherit the parent field name for
        detector matching — not arbitrary nests under keys like credentials.
        """
        data = AuditContextData(
            data_type="test",
            credentials={
                "username": "alice",
                "extra": "metadata",
            },
        )

        sanitized_data = default_sanitizer.sanitize(data)

        assert sanitized_data.credentials == {
            "username": "alice",
            "extra": "metadata",
        }


class TestBooleanPreservation:
    """Test that boolean values are never redacted by key-based detectors (AAP-83652).

    Booleans are forensic metadata (e.g. credential_used, password_set, token_expired)
    and should pass through even when their key matches a sensitive pattern.
    """

    def test_partial_key_preserves_booleans(self) -> None:
        """redact_by_partial_key should not redact boolean values."""
        detector = redact_by_partial_key(["credential", "password", "token"])

        assert detector(True, "credential_used") is None  # noqa: FBT003
        assert detector(False, "credential_used") is None  # noqa: FBT003
        assert detector(True, "password_set") is None  # noqa: FBT003
        assert detector(False, "token_expired") is None  # noqa: FBT003

    def test_camel_case_key_preserves_booleans(self) -> None:
        """redact_by_camel_case_key should not redact boolean values."""
        detector = redact_by_camel_case_key(["credential", "password", "token"])

        assert detector(True, "credentialUsed") is None  # noqa: FBT003
        assert detector(False, "credentialUsed") is None  # noqa: FBT003
        assert detector(True, "passwordSet") is None  # noqa: FBT003
        assert detector(False, "tokenExpired") is None  # noqa: FBT003

    def test_partial_key_still_redacts_strings_for_credential_keys(self) -> None:
        """String values for credential-pattern keys must still be redacted."""
        detector = redact_by_partial_key(["credential", "password"])

        assert detector("my-secret-credential", "credential_value") == REDACTED
        assert detector("hunter2", "password_hash") == REDACTED

    def test_camel_case_still_redacts_strings_for_credential_keys(self) -> None:
        """String values for credential-pattern camelCase keys must still be redacted."""
        detector = redact_by_camel_case_key(["credential", "password"])

        assert detector("my-secret", "credentialValue") == REDACTED
        assert detector("hunter2", "passwordHash") == REDACTED

    def test_sanitizer_preserves_credential_used_boolean(self) -> None:
        """Full sanitizer should preserve credential_used boolean in AuditContextData."""
        from syntara.audit.sanitization import sanitizer

        data = AuditContextData(data_type="aap-resource-access")
        data.credential_used = True

        sanitized = sanitizer.sanitize(data)
        assert sanitized.credential_used is True

    def test_sanitizer_preserves_credential_used_false(self) -> None:
        """Full sanitizer should preserve credential_used=False."""
        from syntara.audit.sanitization import sanitizer

        data = AuditContextData(data_type="aap-resource-access")
        data.credential_used = False

        sanitized = sanitizer.sanitize(data)
        assert sanitized.credential_used is False

    def test_sanitizer_preserves_nested_booleans_with_sensitive_keys(self) -> None:
        """Nested booleans in dicts with credential-pattern keys should be preserved."""
        from syntara.audit.sanitization import sanitizer

        data = AuditContextData(
            data_type="test",
            function_args={
                "credential_used": True,
                "password_set": False,
                "token_expired": True,
                "password_value": "should-be-redacted",
            },
        )

        sanitized = sanitizer.sanitize(data)
        assert sanitized.function_args is not None
        assert sanitized.function_args["credential_used"] is True
        assert sanitized.function_args["password_set"] is False
        assert sanitized.function_args["token_expired"] is True
        assert sanitized.function_args["password_value"] == REDACTED


class TestPIIDetectorType:
    """Test the PIIDetector type alias."""

    def test_custom_detector_implementation(self) -> None:
        """Test implementing a custom detector following the PIIDetector interface."""

        def custom_detector(value: object, key: str) -> str | None:
            if key == "custom_field" and isinstance(value, str):
                return f"[CUSTOM:{len(value)}]"
            return None

        # Verify it matches the PIIDetector type
        detector: PIIDetector = custom_detector

        sanitizer = EventSanitizer(detectors=[detector])
        data = AuditContextData(data_type="test", function_args={"custom_field": "test_data"})

        sanitized_data = sanitizer.sanitize(data)

        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["custom_field"] == "[CUSTOM:9]"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_audit_data(self) -> None:
        """Test sanitization of minimal audit data."""
        sanitizer = EventSanitizer(detectors=[redact_by_partial_key(["password"])])
        data = AuditContextData(data_type="test")

        sanitized_data = sanitizer.sanitize(data)

        assert sanitized_data.error_type is None
        assert sanitized_data.error_message is None

    def test_none_values_in_audit_data(self) -> None:
        """Test handling of None values in audit data."""
        detector = redact_by_partial_key(["secret"])
        sanitizer = EventSanitizer(detectors=[detector])

        # Test separate None values to avoid circular reference issues
        data1 = AuditContextData(data_type="test", function_args={"secret_key": None})
        sanitized_data1 = sanitizer.sanitize(data1)
        assert sanitized_data1.function_args is not None
        assert isinstance(sanitized_data1.function_args, dict)
        assert sanitized_data1.function_args["secret_key"] == REDACTED

        data2 = AuditContextData(data_type="test", function_args={"normal_key": None})
        sanitized_data2 = sanitizer.sanitize(data2)
        assert sanitized_data2.function_args is not None
        assert isinstance(sanitized_data2.function_args, dict)
        assert sanitized_data2.function_args["normal_key"] is None

    def test_nested_empty_structures_in_audit_data(self) -> None:
        """Test handling of nested empty structures in audit data."""
        sanitizer = EventSanitizer()

        empty_structures = {"empty_dict": {}, "empty_list": [], "nested": {"also_empty": {}, "list_empty": []}}
        data = AuditContextData(data_type="test", function_args=empty_structures.copy())

        sanitized_data = sanitizer.sanitize(data)
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args == empty_structures

    def test_deeply_nested_structure_in_audit_data(self) -> None:
        """Test deeply nested structure within depth limit in audit data."""
        sanitizer = EventSanitizer(detectors=[redact_by_partial_key(["secret"])], max_depth=6)

        nested_data = {"level1": {"level2": {"level3": {"level4": {"secret": "should_be_redacted"}}}}}
        data = AuditContextData(data_type="test", function_args=nested_data)

        sanitized_data = sanitizer.sanitize(data)
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["level1"]["level2"]["level3"]["level4"]["secret"] == REDACTED

    def test_mixed_type_lists_in_audit_data(self) -> None:
        """Test lists with mixed types in audit data."""
        sanitizer = EventSanitizer(detectors=[redact_email])

        mixed_list = [
            "john@example.com",
            123,
            {"nested_email": "jane@test.com"},
            None,
            ["nested_list_email@domain.org"],
        ]
        data = AuditContextData(data_type="test", function_args={"mixed_list": mixed_list})

        sanitized_data = sanitizer.sanitize(data)

        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["mixed_list"][0] == "[EMAIL_REDACTED]"
        assert sanitized_data.function_args["mixed_list"][1] == 123
        assert sanitized_data.function_args["mixed_list"][2]["nested_email"] == "[EMAIL_REDACTED]"
        assert sanitized_data.function_args["mixed_list"][3] is None
        assert sanitized_data.function_args["mixed_list"][4][0] == "[EMAIL_REDACTED]"


class TestCircularReferenceHandling:
    """Test comprehensive circular reference detection and handling."""

    def test_primitive_values_can_repeat(self) -> None:
        """Test that primitive values can appear multiple times without being flagged as circular."""
        sanitizer = EventSanitizer()

        # This should NOT be marked as circular since "test" is just a string
        # that appears in two different places
        data = AuditContextData(data_type="test", function_args={"value": "test"}, function_result={"result": "test"})

        sanitized_data = sanitizer.sanitize(data)

        # Both occurrences should preserve the original value
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["value"] == "test"
        assert sanitized_data.function_result is not None
        assert sanitized_data.function_result["result"] == "test"

    def test_multiple_primitive_types_can_repeat(self) -> None:
        """Test that all primitive types can appear multiple times."""
        sanitizer = EventSanitizer()

        primitives = {
            "str1": "test",
            "str2": "test",
            "int1": 42,
            "int2": 42,
            "float1": 3.14,
            "float2": 3.14,
            "bool1": True,
            "bool2": True,
            "none1": None,
            "none2": None,
        }
        data = AuditContextData(data_type="test", function_args=primitives)

        sanitized_data = sanitizer.sanitize(data)

        # All should be preserved without being marked as circular
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["str1"] == "test"
        assert sanitized_data.function_args["str2"] == "test"
        assert sanitized_data.function_args["int1"] == 42
        assert sanitized_data.function_args["int2"] == 42
        assert sanitized_data.function_args["float1"] == 3.14
        assert sanitized_data.function_args["float2"] == 3.14
        assert sanitized_data.function_args["bool1"] is True
        assert sanitized_data.function_args["bool2"] is True
        assert sanitized_data.function_args["none1"] is None
        assert sanitized_data.function_args["none2"] is None

    def test_actual_circular_reference_detection(self) -> None:
        """Test that actual circular references are properly detected."""
        sanitizer = EventSanitizer()

        # Create actual circular reference
        circular_data: dict[str, Any] = {"name": "root"}
        circular_data["self"] = circular_data  # This creates a real circular reference

        data = AuditContextData(data_type="test", function_args={"circular_data": circular_data})

        sanitized_data = sanitizer.sanitize(data)

        # Should detect the circular reference
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["circular_data"]["name"] == "root"
        assert sanitized_data.function_args["circular_data"]["self"] == "[CIRCULAR]"

    def test_shared_object_reference_allowed(self) -> None:
        """Test that the same object shared in multiple places is allowed (not circular)."""
        sanitizer = EventSanitizer()

        shared_list = [1, 2, 3]
        data = AuditContextData(
            data_type="test",
            function_args={
                "list1": shared_list,
                "list2": shared_list,  # Same object in two places - this is NOT circular
            },
        )

        sanitized_data = sanitizer.sanitize(data)

        # Both occurrences should be preserved
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["list1"] == [1, 2, 3]
        assert sanitized_data.function_args["list2"] == [1, 2, 3]

    def test_complex_nested_structure_with_repeated_primitives(self) -> None:
        """Test complex nested structures where primitive values appear multiple times."""
        sanitizer = EventSanitizer()

        user_id = "user123"
        complex_data = {
            "user": {"id": user_id, "preferences": {"theme": "dark", "language": "en"}},
            "session": {
                "user_id": user_id,  # Same string value
                "settings": {
                    "theme": "dark",  # Same string value
                    "auto_save": True,
                },
            },
            "audit": {
                "user_id": user_id,  # Same string value again
                "theme_preference": "dark",  # Same string value again
            },
        }
        data = AuditContextData(data_type="test", function_args=complex_data)

        sanitized_data = sanitizer.sanitize(data)

        # All primitive values should be preserved
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["user"]["id"] == "user123"
        assert sanitized_data.function_args["session"]["user_id"] == "user123"
        assert sanitized_data.function_args["audit"]["user_id"] == "user123"
        assert sanitized_data.function_args["user"]["preferences"]["theme"] == "dark"
        assert sanitized_data.function_args["session"]["settings"]["theme"] == "dark"
        assert sanitized_data.function_args["audit"]["theme_preference"] == "dark"

    def test_mixed_shared_objects_and_circular_references(self) -> None:
        """Test scenario with both shared objects and actual circular references."""
        sanitizer = EventSanitizer()

        # Create a structure with shared objects (allowed) and actual circular references
        shared_dict = {"value": "shared_string"}
        circular_dict: dict[str, Any] = {"name": "circular"}
        circular_dict["self"] = circular_dict  # True circular reference

        mixed_data = {
            "string1": "shared_string",  # Repeated primitive - should be OK
            "string2": "shared_string",  # Repeated primitive - should be OK
            "dict1": shared_dict,  # First reference to shared object - OK
            "dict2": shared_dict,  # Second reference to shared object - OK (not circular)
            "circular": circular_dict,  # Object with circular reference
        }
        data = AuditContextData(data_type="test", function_args=mixed_data)

        sanitized_data = sanitizer.sanitize(data)

        # Primitives should be preserved
        assert sanitized_data.function_args is not None
        assert isinstance(sanitized_data.function_args, dict)
        assert sanitized_data.function_args["string1"] == "shared_string"
        assert sanitized_data.function_args["string2"] == "shared_string"

        # Shared object references should both be preserved (not circular)
        assert sanitized_data.function_args["dict1"]["value"] == "shared_string"
        assert sanitized_data.function_args["dict2"]["value"] == "shared_string"

        # But actual circular reference should be detected
        assert sanitized_data.function_args["circular"]["name"] == "circular"
        assert sanitized_data.function_args["circular"]["self"] == "[CIRCULAR]"
