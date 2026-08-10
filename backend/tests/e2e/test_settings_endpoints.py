"""E2E tests for settings API endpoints."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from orchestrator_test_sdk.e2e.helpers import _retry_api_call
from syntara_api_client.models.error_data import ErrorData
from syntara_api_client.models.runtime_setting_read import RuntimeSettingRead
from syntara_api_client.models.setting_bulk_update_item import SettingBulkUpdateItem
from syntara_api_client.models.setting_bulk_update_request import SettingBulkUpdateRequest
from syntara_api_client.models.setting_update import SettingUpdate

if TYPE_CHECKING:
    from syntara_api_client.api import SyntaraApiRegistry

pytestmark = [pytest.mark.e2e]

_LOG_LEVEL_KEY = "logging.log_level"
_MAX_TOKENS_KEY = "context_manager.max_total_tokens"
_GROUNDING_SCORE_KEY = "context_manager.required_grounding_score"
_ENABLE_HYBRID_KEY = "context_manager.enable_hybrid_search"
_COMPRESSION_TEMP_KEY = "context_manager.compression_temperature"
_TIMEOUT_SECONDS_KEY = "document_conversion.timeout_seconds"
_SCRIPT_TIMEOUT_KEY = "workflow_engine.script_timeout_seconds"
_OVERWRITE_KEY = "document_conversion.overwrite_existing"


def _get_setting(api: SyntaraApiRegistry, key: str) -> RuntimeSettingRead:
    """Get a single setting, asserting success."""
    setting = _retry_api_call(lambda: api.settings.get(key=key)).assert_and_get()
    assert isinstance(setting, RuntimeSettingRead)
    return setting


def _update_setting(
    api: SyntaraApiRegistry,
    key: str,
    value: object,
    *,
    expected_version: int | None = None,
) -> RuntimeSettingRead:
    """Update a single setting, asserting success."""
    body = SettingUpdate(value=value)
    if expected_version is not None:
        body.expected_version = expected_version
    setting = _retry_api_call(lambda: api.settings.update(key=key, body=body)).assert_and_get()
    assert isinstance(setting, RuntimeSettingRead)
    return setting


def _restore_setting(api: SyntaraApiRegistry, key: str, value: object) -> None:
    """Restore a setting to a previous value (best-effort, no assertions)."""
    api.settings.update(key=key, body=SettingUpdate(value=value))


@pytest.mark.xdist_group("settings_write")
class TestSettings:
    """E2E tests for settings GET and PATCH endpoints."""

    def test_list_settings(self, syntara_api: SyntaraApiRegistry) -> None:
        """GET /settings returns 200 with resources containing required fields."""
        settings_list = syntara_api.settings.list().assert_and_get()
        settings = settings_list.resources
        assert len(settings) > 0
        for setting in settings:
            assert setting.key
            assert setting.effective_value is not None
            assert setting.value_type is not None
            assert setting.category
            assert setting.version is not None

    def test_list_categories(self, syntara_api: SyntaraApiRegistry) -> None:
        """GET /settings/categories returns 200 with all expected categories."""
        categories_response = syntara_api.settings.list_categories().assert_and_get()
        categories = categories_response.resources
        assert len(categories) > 0
        slugs = [cat.slug for cat in categories]
        for expected in ("ai_llm", "system", "context_manager", "workflow_execution", "application"):
            assert expected in slugs
        for cat in categories:
            assert cat.slug
            assert cat.name
            assert cat.group_names is not None

    def test_get_setting(self, syntara_api: SyntaraApiRegistry) -> None:
        """GET /settings/{key} returns a specific setting with full metadata."""
        setting = _get_setting(syntara_api, _MAX_TOKENS_KEY)

        assert setting.key == _MAX_TOKENS_KEY
        assert setting.effective_value is not None
        assert setting.default_value is not None
        assert setting.value_type is not None
        assert setting.category
        assert setting.version is not None
        assert setting.validation_schema is not None

    def test_update_setting(self, syntara_api: SyntaraApiRegistry) -> None:
        """PATCH /settings/{key} updates a setting and persists on re-read."""
        original_value = _get_setting(syntara_api, _MAX_TOKENS_KEY).effective_value

        try:
            updated = _update_setting(syntara_api, _MAX_TOKENS_KEY, 6666)
            assert updated.effective_value == 6666

            reread = _get_setting(syntara_api, _MAX_TOKENS_KEY)
            assert reread.effective_value == 6666
        finally:
            _restore_setting(syntara_api, _MAX_TOKENS_KEY, original_value)


@pytest.mark.xdist_group("settings_write")
class TestLogLevelSetting:
    """E2E tests for the logging.log_level runtime setting."""

    def test_get_log_level(self, syntara_api: SyntaraApiRegistry) -> None:
        """Admin can read the log level setting with expected metadata."""
        setting = _get_setting(syntara_api, _LOG_LEVEL_KEY)

        assert setting.key == _LOG_LEVEL_KEY
        assert setting.requires_restart is False
        assert setting.effective_value in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    def test_update_log_level(self, syntara_api: SyntaraApiRegistry) -> None:
        """Admin can change the log level and the update persists on re-read."""
        original_value = _get_setting(syntara_api, _LOG_LEVEL_KEY).effective_value

        try:
            updated = _update_setting(syntara_api, _LOG_LEVEL_KEY, "DEBUG")
            assert updated.effective_value == "DEBUG"

            reread = _get_setting(syntara_api, _LOG_LEVEL_KEY)
            assert reread.effective_value == "DEBUG"
        finally:
            _restore_setting(syntara_api, _LOG_LEVEL_KEY, original_value)

    def test_update_log_level_rejects_invalid(self, syntara_api: SyntaraApiRegistry) -> None:
        """Updating log level with an invalid value returns 422."""
        resp = syntara_api.settings.update(key=_LOG_LEVEL_KEY, body=SettingUpdate(value="INVALID"))

        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestNewSettings:
    """E2E tests for runtime settings catalog entries."""

    def test_new_categories_appear(self, syntara_api: SyntaraApiRegistry) -> None:
        """GET /settings/categories includes ai_llm, workflow_execution, application."""
        categories_response = syntara_api.settings.list_categories().assert_and_get()
        slugs = [cat.slug for cat in categories_response.resources]
        assert "ai_llm" in slugs
        assert "workflow_execution" in slugs
        assert "application" in slugs

    def test_workflow_setting_exists(self, syntara_api: SyntaraApiRegistry) -> None:
        """GET /settings/{key} returns a workflow execution setting."""
        setting = _get_setting(syntara_api, _SCRIPT_TIMEOUT_KEY)

        assert setting.key == _SCRIPT_TIMEOUT_KEY
        assert setting.category == "workflow_execution"
        assert setting.value_type.value == "integer"
        assert setting.default_value == 300

    def test_all_settings_have_requires_restart(self, syntara_api: SyntaraApiRegistry) -> None:
        """Every setting in the list response includes a requires_restart boolean."""
        settings_list = syntara_api.settings.list().assert_and_get()
        for setting in settings_list.resources:
            assert isinstance(setting.requires_restart, bool)

    def test_constraint_validation_rejects_invalid(self, syntara_api: SyntaraApiRegistry) -> None:
        """PATCH with out-of-range value returns 422."""
        resp = syntara_api.settings.update(key=_TIMEOUT_SECONDS_KEY, body=SettingUpdate(value=999))

        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestAuditorSettingsAccess:
    """E2E tests verifying auditor users have read-only access to settings."""

    def test_auditor_can_list_settings(self, auditor_api: SyntaraApiRegistry) -> None:
        """Auditor can list all settings."""
        settings_list = auditor_api.settings.list().assert_and_get()
        assert len(settings_list.resources) > 0

    def test_auditor_can_get_setting(self, auditor_api: SyntaraApiRegistry) -> None:
        """Auditor can read a specific setting."""
        setting = auditor_api.settings.get(key=_MAX_TOKENS_KEY).assert_and_get()
        assert isinstance(setting, RuntimeSettingRead)
        assert setting.key == _MAX_TOKENS_KEY

    def test_auditor_can_list_categories(self, auditor_api: SyntaraApiRegistry) -> None:
        """Auditor can list setting categories."""
        categories_response = auditor_api.settings.list_categories().assert_and_get()
        assert len(categories_response.resources) > 0

    def test_auditor_cannot_update_setting(self, auditor_api: SyntaraApiRegistry) -> None:
        """Auditor is denied access to update a setting."""
        resp = auditor_api.settings.update(key=_LOG_LEVEL_KEY, body=SettingUpdate(value="DEBUG"))

        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_auditor_cannot_bulk_update(self, auditor_api: SyntaraApiRegistry) -> None:
        """Auditor is denied access to bulk update settings."""
        resp = auditor_api.settings.bulk_update(
            body=SettingBulkUpdateRequest(updates=[SettingBulkUpdateItem(key=_LOG_LEVEL_KEY, value="DEBUG")])
        )

        assert resp.status_code == HTTPStatus.FORBIDDEN


class TestSettingsAuthorization:
    """E2E tests verifying non-admin users cannot access settings."""

    def test_viewer_cannot_list_settings(self, viewer_api: SyntaraApiRegistry) -> None:
        """Non-admin user is denied access to list settings."""
        resp = viewer_api.settings.list()
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_viewer_cannot_get_setting(self, viewer_api: SyntaraApiRegistry) -> None:
        """Non-admin user is denied access to read a specific setting."""
        resp = viewer_api.settings.get(key=_LOG_LEVEL_KEY)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_viewer_cannot_update_setting(self, viewer_api: SyntaraApiRegistry) -> None:
        """Non-admin user is denied access to update a setting."""
        resp = viewer_api.settings.update(key=_LOG_LEVEL_KEY, body=SettingUpdate(value="DEBUG"))
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_viewer_cannot_bulk_update(self, viewer_api: SyntaraApiRegistry) -> None:
        """Non-admin user is denied access to bulk update settings."""
        resp = viewer_api.settings.bulk_update(
            body=SettingBulkUpdateRequest(updates=[SettingBulkUpdateItem(key=_LOG_LEVEL_KEY, value="DEBUG")])
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_viewer_cannot_list_categories(self, viewer_api: SyntaraApiRegistry) -> None:
        """Non-admin user is denied access to list setting categories."""
        resp = viewer_api.settings.list_categories()
        assert resp.status_code == HTTPStatus.FORBIDDEN


class TestSettingsFiltering:
    """E2E tests for filtering settings by category and group."""

    def test_filter_by_category(self, syntara_api: SyntaraApiRegistry) -> None:
        """GET /settings?category= returns only settings in that category."""
        settings_list = syntara_api.settings.list(category="context_manager").assert_and_get()
        settings = settings_list.resources
        assert len(settings) > 0
        for setting in settings:
            assert setting.category == "context_manager"

    def test_filter_by_category_and_group(self, syntara_api: SyntaraApiRegistry) -> None:
        """GET /settings?category=&group= returns only matching settings."""
        settings_list = syntara_api.settings.list(category="context_manager", group="Compression").assert_and_get()
        settings = settings_list.resources
        assert len(settings) > 0
        for setting in settings:
            assert setting.category == "context_manager"
            assert setting.group == "Compression"


class TestSettingsPagination:
    """E2E tests for cursor-based pagination of settings."""

    def test_pagination_no_overlap(self, syntara_api: SyntaraApiRegistry) -> None:
        """Paginated pages do not contain overlapping settings."""
        # sort by -created_at to align with the cursor's (created_at, id) keyset
        page1_response = syntara_api.settings.list(limit=5, sort="-created_at").assert_and_get()
        assert len(page1_response.resources) == 5
        assert page1_response.next_ is not None

        page2_response = syntara_api.settings.list(
            limit=5, sort="-created_at", cursor=page1_response.next_
        ).assert_and_get()
        assert len(page2_response.resources) > 0

        page1_keys = {s.key for s in page1_response.resources}
        page2_keys = {s.key for s in page2_response.resources}
        assert page1_keys.isdisjoint(page2_keys)


class TestSettingsGetErrors:
    """E2E tests for error responses on GET /settings/{key}."""

    def test_get_nonexistent_setting_404(self, syntara_api: SyntaraApiRegistry) -> None:
        """Requesting a nonexistent setting key returns 404."""
        resp = syntara_api.settings.get(key="nonexistent.setting.key")
        assert resp.status_code == HTTPStatus.NOT_FOUND

    def test_get_invalid_key_format_400(self, syntara_api: SyntaraApiRegistry) -> None:
        """Requesting a setting with an invalid key format returns 400."""
        resp = syntara_api.settings.get(key="INVALID")
        assert resp.status_code == HTTPStatus.BAD_REQUEST


class TestSettingsValidation:
    """E2E tests for setting value validation on PATCH."""

    def test_float_above_max(self, syntara_api: SyntaraApiRegistry) -> None:
        """Float value above max constraint returns 422."""
        resp = syntara_api.settings.update(key=_GROUNDING_SCORE_KEY, body=SettingUpdate(value=1.5))
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_float_below_min(self, syntara_api: SyntaraApiRegistry) -> None:
        """Float value below min constraint returns 422."""
        resp = syntara_api.settings.update(key=_GROUNDING_SCORE_KEY, body=SettingUpdate(value=-0.1))
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_wrong_type_string_for_boolean(self, syntara_api: SyntaraApiRegistry) -> None:
        """String value for a boolean setting returns 422."""
        resp = syntara_api.settings.update(key=_ENABLE_HYBRID_KEY, body=SettingUpdate(value="yes"))
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_boolean_for_integer(self, syntara_api: SyntaraApiRegistry) -> None:
        """Boolean value for an integer setting returns 422."""
        resp = syntara_api.settings.update(key=_MAX_TOKENS_KEY, body=SettingUpdate(value=True))
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_integer_below_min(self, syntara_api: SyntaraApiRegistry) -> None:
        """Integer value below min constraint returns 422 with descriptive message."""
        resp = syntara_api.settings.update(key=_MAX_TOKENS_KEY, body=SettingUpdate(value=0))

        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert isinstance(resp.parsed, ErrorData)
        assert "must be >= 1" in resp.parsed.detail

    def test_null_value_rejected(self, syntara_api: SyntaraApiRegistry) -> None:
        """Null value returns 422 with guidance to use default_value."""
        resp = syntara_api.settings.update(key=_LOG_LEVEL_KEY, body=SettingUpdate(value=None))

        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert isinstance(resp.parsed, ErrorData)
        assert "default_value" in resp.parsed.detail

    def test_nonexistent_key_on_update(self, syntara_api: SyntaraApiRegistry) -> None:
        """Updating a nonexistent setting key returns 404."""
        resp = syntara_api.settings.update(key="nonexistent.setting.key", body=SettingUpdate(value=42))
        assert resp.status_code == HTTPStatus.NOT_FOUND

    def test_oversized_value(self, syntara_api: SyntaraApiRegistry) -> None:
        """Value exceeding 64KB returns 422."""
        resp = syntara_api.settings.update(key="telemetry.segment_endpoint", body=SettingUpdate(value="x" * 70_000))
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.xdist_group("settings_write")
class TestSettingsResetToDefault:
    """E2E tests for resetting a setting to its default value."""

    def test_reset_to_default(self, syntara_api: SyntaraApiRegistry) -> None:
        """Setting can be reset by PATCHing with its default_value."""
        original_value = _get_setting(syntara_api, _MAX_TOKENS_KEY).effective_value

        try:
            _update_setting(syntara_api, _MAX_TOKENS_KEY, 9999)
            default_value = _get_setting(syntara_api, _MAX_TOKENS_KEY).default_value
            _update_setting(syntara_api, _MAX_TOKENS_KEY, default_value)

            result = _get_setting(syntara_api, _MAX_TOKENS_KEY)
            assert result.effective_value == default_value
        finally:
            _restore_setting(syntara_api, _MAX_TOKENS_KEY, original_value)


@pytest.mark.xdist_group("settings_write")
class TestSettingsBulkUpdate:
    """E2E tests for the bulk update endpoint PATCH /settings."""

    def test_bulk_update_happy_path(self, syntara_api: SyntaraApiRegistry) -> None:
        """Bulk update across categories succeeds and persists."""
        keys = [_MAX_TOKENS_KEY, _SCRIPT_TIMEOUT_KEY, _TIMEOUT_SECONDS_KEY]
        originals = {k: _get_setting(syntara_api, k).effective_value for k in keys}

        try:
            updated_settings = syntara_api.settings.bulk_update(
                body=SettingBulkUpdateRequest(
                    updates=[
                        SettingBulkUpdateItem(key=_MAX_TOKENS_KEY, value=5000),
                        SettingBulkUpdateItem(key=_SCRIPT_TIMEOUT_KEY, value=60),
                        SettingBulkUpdateItem(key=_TIMEOUT_SECONDS_KEY, value=15),
                    ]
                )
            ).assert_and_get()
            assert isinstance(updated_settings.resources, list)
            assert len(updated_settings.resources) == 3

            for key, expected in [
                (_MAX_TOKENS_KEY, 5000),
                (_SCRIPT_TIMEOUT_KEY, 60),
                (_TIMEOUT_SECONDS_KEY, 15),
            ]:
                assert _get_setting(syntara_api, key).effective_value == expected
        finally:
            for k, v in originals.items():
                _restore_setting(syntara_api, k, v)

    def test_bulk_update_all_or_nothing(self, syntara_api: SyntaraApiRegistry) -> None:
        """If any item in a bulk update fails validation, no settings change."""
        original_tokens = _get_setting(syntara_api, _MAX_TOKENS_KEY).effective_value
        original_grounding = _get_setting(syntara_api, _GROUNDING_SCORE_KEY).effective_value

        try:
            resp = syntara_api.settings.bulk_update(
                body=SettingBulkUpdateRequest(
                    updates=[
                        SettingBulkUpdateItem(key=_MAX_TOKENS_KEY, value=5000),
                        SettingBulkUpdateItem(key=_GROUNDING_SCORE_KEY, value=999.0),
                    ]
                )
            )
            assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

            assert _get_setting(syntara_api, _MAX_TOKENS_KEY).effective_value == original_tokens
            assert _get_setting(syntara_api, _GROUNDING_SCORE_KEY).effective_value == original_grounding
        finally:
            _restore_setting(syntara_api, _MAX_TOKENS_KEY, original_tokens)
            _restore_setting(syntara_api, _GROUNDING_SCORE_KEY, original_grounding)

    def test_bulk_update_duplicate_keys(self, syntara_api: SyntaraApiRegistry) -> None:
        """Bulk update with duplicate keys returns 400 with message."""
        resp = syntara_api.settings.bulk_update(
            body=SettingBulkUpdateRequest(
                updates=[
                    SettingBulkUpdateItem(key=_MAX_TOKENS_KEY, value=1000),
                    SettingBulkUpdateItem(key=_MAX_TOKENS_KEY, value=2000),
                ]
            )
        )

        assert resp.status_code == HTTPStatus.BAD_REQUEST
        assert isinstance(resp.parsed, ErrorData)
        assert "duplicate" in resp.parsed.detail.lower()

    def test_bulk_update_empty_list(self, syntara_api: SyntaraApiRegistry) -> None:
        """Bulk update with empty updates list returns 200."""
        updated_settings = syntara_api.settings.bulk_update(body=SettingBulkUpdateRequest(updates=[])).assert_and_get()
        assert updated_settings.resources == []

    def test_bulk_update_exceeds_limit(self, syntara_api: SyntaraApiRegistry) -> None:
        """Bulk update with more than 500 items returns 422."""
        updates = [SettingBulkUpdateItem(key=f"fake.key_{i}", value=i) for i in range(501)]
        resp = syntara_api.settings.bulk_update(body=SettingBulkUpdateRequest(updates=updates))

        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_bulk_update_version_conflict(self, syntara_api: SyntaraApiRegistry) -> None:
        """Bulk update with a stale version returns 409 and no settings change."""
        setting_a = _get_setting(syntara_api, _MAX_TOKENS_KEY)
        setting_b = _get_setting(syntara_api, _COMPRESSION_TEMP_KEY)
        original_a = setting_a.effective_value

        try:
            incremented = _update_setting(syntara_api, _COMPRESSION_TEMP_KEY, 0.5, expected_version=setting_b.version)

            resp = syntara_api.settings.bulk_update(
                body=SettingBulkUpdateRequest(
                    updates=[
                        SettingBulkUpdateItem(key=_MAX_TOKENS_KEY, value=7777),
                        SettingBulkUpdateItem(
                            key=_COMPRESSION_TEMP_KEY,
                            value=0.9,
                            expected_version=setting_b.version,
                        ),
                    ]
                )
            )
            assert resp.status_code == HTTPStatus.CONFLICT
            assert isinstance(resp.parsed, ErrorData)
            assert resp.parsed.code == "SETTING_VERSION_CONFLICT"

            assert _get_setting(syntara_api, _MAX_TOKENS_KEY).effective_value == original_a
            assert _get_setting(syntara_api, _COMPRESSION_TEMP_KEY).effective_value == incremented.effective_value
        finally:
            _restore_setting(syntara_api, _MAX_TOKENS_KEY, original_a)
            _restore_setting(syntara_api, _COMPRESSION_TEMP_KEY, setting_b.effective_value)


@pytest.mark.xdist_group("settings_write")
class TestSettingsOptimisticLocking:
    """E2E tests for optimistic locking via expected_version."""

    def test_correct_version(self, syntara_api: SyntaraApiRegistry) -> None:
        """Update with correct expected_version succeeds and increments version."""
        setting = _get_setting(syntara_api, _COMPRESSION_TEMP_KEY)
        original_value = setting.effective_value
        version_n = setting.version

        try:
            updated = _update_setting(syntara_api, _COMPRESSION_TEMP_KEY, 0.5, expected_version=version_n)
            assert updated.version == version_n + 1
        finally:
            _restore_setting(syntara_api, _COMPRESSION_TEMP_KEY, original_value)

    def test_stale_version(self, syntara_api: SyntaraApiRegistry) -> None:
        """Update with stale expected_version returns 409."""
        setting = _get_setting(syntara_api, _COMPRESSION_TEMP_KEY)
        original_value = setting.effective_value
        version_n = setting.version

        try:
            _update_setting(syntara_api, _COMPRESSION_TEMP_KEY, 0.5, expected_version=version_n)

            resp = syntara_api.settings.update(
                key=_COMPRESSION_TEMP_KEY,
                body=SettingUpdate(value=0.9, expected_version=version_n),
            )
            assert resp.status_code == HTTPStatus.CONFLICT
            assert isinstance(resp.parsed, ErrorData)
            assert resp.parsed.code == "SETTING_VERSION_CONFLICT"
        finally:
            _restore_setting(syntara_api, _COMPRESSION_TEMP_KEY, original_value)

    def test_without_expected_version(self, syntara_api: SyntaraApiRegistry) -> None:
        """Update without expected_version succeeds and increments version."""
        setting = _get_setting(syntara_api, _COMPRESSION_TEMP_KEY)
        original_value = setting.effective_value
        version_n = setting.version

        try:
            updated = _update_setting(syntara_api, _COMPRESSION_TEMP_KEY, 0.5)
            assert updated.version == version_n + 1
        finally:
            _restore_setting(syntara_api, _COMPRESSION_TEMP_KEY, original_value)


@pytest.mark.xdist_group("settings_write")
class TestAdminSettingsAccess:
    """E2E test verifying admin has full CRUD access to all settings endpoints."""

    def test_admin_full_access(self, syntara_api: SyntaraApiRegistry) -> None:
        """Admin can list, get, list categories, update, and bulk update settings."""
        assert syntara_api.settings.list().status_code == HTTPStatus.OK
        assert syntara_api.settings.list_categories().status_code == HTTPStatus.OK
        assert syntara_api.settings.get(key=_MAX_TOKENS_KEY).status_code == HTTPStatus.OK

        original = _get_setting(syntara_api, _MAX_TOKENS_KEY).effective_value
        try:
            assert (
                syntara_api.settings.update(key=_MAX_TOKENS_KEY, body=SettingUpdate(value=5555)).status_code
                == HTTPStatus.OK
            )
            assert (
                syntara_api.settings.bulk_update(
                    body=SettingBulkUpdateRequest(updates=[SettingBulkUpdateItem(key=_MAX_TOKENS_KEY, value=6666)])
                ).status_code
                == HTTPStatus.OK
            )
        finally:
            _restore_setting(syntara_api, _MAX_TOKENS_KEY, original)


@pytest.mark.xdist_group("settings_write")
class TestWorkflowExecutionSetting:
    """E2E tests for workflow execution settings."""

    def test_update_workflow_setting(self, syntara_api: SyntaraApiRegistry) -> None:
        """Update a workflow execution setting with full GET-PATCH-GET-restore flow."""
        original = _get_setting(syntara_api, _SCRIPT_TIMEOUT_KEY)
        original_value = original.effective_value

        assert original.category == "workflow_execution"
        assert original.value_type.value == "integer"

        try:
            updated = _update_setting(syntara_api, _SCRIPT_TIMEOUT_KEY, 60)
            assert updated.effective_value == 60

            reread = _get_setting(syntara_api, _SCRIPT_TIMEOUT_KEY)
            assert reread.effective_value == 60
        finally:
            _restore_setting(syntara_api, _SCRIPT_TIMEOUT_KEY, original_value)


@pytest.mark.xdist_group("settings_write")
class TestApplicationSetting:
    """E2E tests for application category settings."""

    def test_update_application_setting(self, syntara_api: SyntaraApiRegistry) -> None:
        """Update an application setting and verify persistence."""
        original = _get_setting(syntara_api, _OVERWRITE_KEY)
        original_value = original.effective_value

        assert original.category == "application"
        assert original.value_type.value == "boolean"

        try:
            updated = _update_setting(syntara_api, _OVERWRITE_KEY, value=True)
            assert updated.effective_value is True

            reread = _get_setting(syntara_api, _OVERWRITE_KEY)
            assert reread.effective_value is True
        finally:
            _restore_setting(syntara_api, _OVERWRITE_KEY, original_value)
