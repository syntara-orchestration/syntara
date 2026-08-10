"""Tests for InjectorResolver — {{field_id}} template resolution."""

from syntara.credentials.lib.injector_resolver import InjectorResolver, ResolvedInjectors


class TestResolveTemplates:
    """Test {{field_id}} template substitution."""

    def test_bearer_token_resolution(self) -> None:
        injectors = {"extra_vars": {"auth_type": "bearer", "bearer_token": "{{token}}"}, "env": {}, "file": {}}
        inputs = {"token": "sk-abc-123"}
        result = InjectorResolver.resolve(injectors, inputs)
        assert result.extra_vars == {"auth_type": "bearer", "bearer_token": "sk-abc-123"}

    def test_basic_auth_resolution(self) -> None:
        injectors = {
            "extra_vars": {"basic_username": "{{username}}", "basic_password": "{{password}}"},
            "env": {},
            "file": {},
        }
        inputs = {"username": "admin", "password": "secret"}
        result = InjectorResolver.resolve(injectors, inputs)
        assert result.extra_vars["basic_username"] == "admin"
        assert result.extra_vars["basic_password"] == "secret"  # noqa: S105

    def test_missing_field_resolves_to_empty(self) -> None:
        injectors = {"extra_vars": {"token": "{{token}}", "host": "{{host}}"}, "env": {}, "file": {}}
        inputs = {"token": "abc"}
        result = InjectorResolver.resolve(injectors, inputs)
        assert result.extra_vars["token"] == "abc"  # noqa: S105
        assert result.extra_vars["host"] == ""

    def test_static_values_unchanged(self) -> None:
        injectors = {"extra_vars": {"auth_type": "bearer"}, "env": {}, "file": {}}
        result = InjectorResolver.resolve(injectors, {})
        assert result.extra_vars["auth_type"] == "bearer"

    def test_env_section(self) -> None:
        injectors = {"extra_vars": {}, "env": {"API_KEY": "{{api_key}}"}, "file": {}}
        inputs = {"api_key": "key-123"}
        result = InjectorResolver.resolve(injectors, inputs)
        assert result.env["API_KEY"] == "key-123"

    def test_file_section(self) -> None:
        injectors = {"extra_vars": {}, "env": {}, "file": {"ssh_key": "{{ssh_private_key}}"}}
        inputs = {"ssh_private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n..."}
        result = InjectorResolver.resolve(injectors, inputs)
        assert result.file["ssh_key"].startswith("-----BEGIN")

    def test_empty_injectors(self) -> None:
        result = InjectorResolver.resolve({}, {"token": "abc"})
        assert result == ResolvedInjectors()

    def test_none_field_resolves_to_empty(self) -> None:
        injectors = {"extra_vars": {"val": "{{field}}"}, "env": {}, "file": {}}
        inputs = {"field": None}
        result = InjectorResolver.resolve(injectors, inputs)
        assert result.extra_vars["val"] == ""

    def test_boolean_field_resolves_to_string(self) -> None:
        injectors = {"extra_vars": {"ssl": "{{verify_ssl}}"}, "env": {}, "file": {}}
        inputs = {"verify_ssl": True}
        result = InjectorResolver.resolve(injectors, inputs)
        assert result.extra_vars["ssl"] == "True"
