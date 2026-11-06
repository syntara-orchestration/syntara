"""Plugin installation: artifact validation pipeline and installed queries.

Plugins are installed from two sources, both funneling into one validation
pipeline:

- **Registry install** (``install_plugin``): the artifact is re-read from an
  OCI registry by the immutable digest recorded in the catalog, and the
  descriptor identity is cross-checked against the catalog entry.
- **Archive upload** (``install_from_upload``): a ``.oci.tar`` built by
  ``syntara-plugin build`` is unpacked in memory; the manifest digest is
  cross-checked against the archive's own ``index.json`` and the descriptor
  identity against the manifest annotations. No registry is involved.

The pipeline records every passed check in a validation report stored with
the installed plugin:

1. The artifact manifest is read by its immutable digest reference.
2. The artifact type must be the Syntara plugin artifact type.
3. The config blob is read and its media type verified.
4. The plugin descriptor layer is read, hash-verified, and parsed; its
   identity must match the expected identity and the digest recorded in the
   artifact config.
5. The content bundle is read and hash-verified.
6. The documentation file named by the descriptor is extracted from the
   content bundle and its digest verified.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models.user import User
from syntara.core.services.base import BaseService
from syntara.plugins.exceptions import (
    PluginArtifactValidationError,
    PluginNotFoundError,
    PluginRegistryValidationError,
    PluginVersionConflictError,
)
from syntara.plugins.models.installed_plugin import (
    InstalledPlugin,
    InstalledPluginListResponse,
    PluginInstallStatus,
)
from syntara.plugins.models.marketplace_plugin import MarketplacePlugin
from syntara.plugins.models.plugin_catalog_source import PluginCatalogSource
from syntara.plugins.services.artifacts import (
    PLUGIN_ARTIFACT_TYPE,
    PLUGIN_CONFIG_MEDIA_TYPE,
    PLUGIN_CONTENT_MEDIA_TYPE,
    PLUGIN_MANIFEST_MEDIA_TYPE,
    documentation_path,
    extract_file,
    parse_json,
    summarize_targets,
)
from syntara.plugins.services.oci_archive import OciArchiveClient
from syntara.plugins.services.oci_client import (
    OciRegistryClient,
    descriptor_digest,
    descriptor_media_type,
    find_layer_by_media_type,
)

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ArtifactValidationResult:
    """Outcome of the plugin artifact validation pipeline."""

    report: list[dict[str, Any]] = field(default_factory=list)
    descriptor: dict[str, Any] = field(default_factory=dict)
    documentation: str | None = None

    def record(self, check: str, detail: str) -> None:
        """Append one passed check to the report."""
        self.report.append({"check": check, "status": "passed", "detail": detail})


@dataclass
class ArtifactExpectation:
    """What the validation pipeline cross-checks an artifact against.

    ``namespace``/``plugin_name``/``version`` may be ``None`` (archive
    uploads without manifest annotations); those cross-checks are then
    skipped, but the descriptor must still declare them.
    """

    repository: str
    artifact_digest: str
    namespace: str | None = None
    plugin_name: str | None = None
    version: str | None = None
    documentation_digest: str | None = None


class ArtifactReader(Protocol):
    """Minimal blob/manifest surface shared by registry and archive clients."""

    async def get_manifest(self, repository: str, reference: str) -> tuple[dict[str, Any], str, bytes]:
        """Return one manifest document, its verified digest, and raw bytes."""

    async def get_blob(self, repository: str, digest: str) -> bytes:
        """Return one blob's content, verified against its digest."""


class PluginInstallService(BaseService):
    """Service for installing, uninstalling, and querying installed plugins."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Create the service with a database session and requesting user."""
        super().__init__(session, user)

    # ------------------------------------------------------------------
    # Install entry points
    # ------------------------------------------------------------------

    async def install_plugin(self, marketplace_plugin_id: UUID) -> InstalledPlugin:
        """Validate and install one marketplace plugin.

        Idempotent for the same artifact digest; a different version of an
        installed plugin is rejected with a version conflict.
        """
        marketplace = await self.session.get(MarketplacePlugin, marketplace_plugin_id)
        if marketplace is None:
            msg = "Marketplace plugin"
            raise PluginNotFoundError(msg, marketplace_plugin_id)
        source = await self.session.get(PluginCatalogSource, marketplace.catalog_source_id)
        if source is None:
            msg1 = "catalog-source"
            msg2 = "the catalog source for this plugin no longer exists"
            raise PluginArtifactValidationError(msg1, msg2)

        existing = await self._installed_for(marketplace.namespace, marketplace.plugin_name)
        if existing is not None:
            if existing.artifact_digest == marketplace.artifact_digest:
                return existing
            raise PluginVersionConflictError(marketplace.namespace, marketplace.plugin_name, existing.version)

        client = OciRegistryClient(source.registry_origin, username=source.username, password=source.password)
        expectation = ArtifactExpectation(
            repository=marketplace.artifact_repository,
            artifact_digest=marketplace.artifact_digest,
            namespace=marketplace.namespace,
            plugin_name=marketplace.plugin_name,
            version=marketplace.version,
            documentation_digest=marketplace.documentation_digest,
        )
        return await self._create_installed(client, expectation)

    async def install_from_upload(self, filename: str, content: bytes) -> InstalledPlugin:
        """Validate and install a plugin directly from an uploaded ``.oci.tar``.

        The archive is unpacked in memory; every blob must hash to its
        declared digest, the manifest must match the archive index, and the
        descriptor identity must match the manifest annotations. Idempotent
        for the same artifact digest, mirroring registry installs.
        """
        try:
            archive = OciArchiveClient(content, filename=filename)
        except PluginRegistryValidationError as error:
            msg = "archive"
            raise PluginArtifactValidationError(msg, error.message) from error

        namespace, name, _version = archive.annotation_identity()
        expectation = ArtifactExpectation(
            repository=filename,
            artifact_digest=archive.manifest_digest,
            namespace=namespace,
            plugin_name=name,
        )

        existing: InstalledPlugin | None = None
        if namespace is not None and name is not None:
            existing = await self._installed_for(namespace, name)
            if existing is not None and existing.artifact_digest != archive.manifest_digest:
                raise PluginVersionConflictError(namespace, name, existing.version)

        return await self._create_installed(archive, expectation, existing)

    # ------------------------------------------------------------------
    # Shared install mechanics
    # ------------------------------------------------------------------

    async def _installed_for(self, namespace: str, plugin_name: str) -> InstalledPlugin | None:
        """Return the installed plugin for one (namespace, name) identity, if any."""
        return (
            await self.session.exec(
                select(InstalledPlugin).where(
                    col(InstalledPlugin.namespace) == namespace,
                    col(InstalledPlugin.plugin_name) == plugin_name,
                )
            )
        ).first()

    async def _create_installed(
        self,
        client: ArtifactReader,
        expectation: ArtifactExpectation,
        prechecked_existing: InstalledPlugin | None = None,
    ) -> InstalledPlugin:
        """Run the validation pipeline and persist the installed plugin."""
        if prechecked_existing is not None:
            return prechecked_existing

        validation = await self._run_pipeline(client, expectation)
        metadata = validation.descriptor.get("metadata")
        if not isinstance(metadata, dict):
            msg1 = "descriptor-metadata"
            msg2 = "descriptor has no metadata"
            raise PluginArtifactValidationError(msg1, msg2)
        namespace = metadata.get("namespace")
        plugin_name = metadata.get("name")
        version = metadata.get("version")
        if not (
            isinstance(namespace, str)
            and namespace
            and isinstance(plugin_name, str)
            and plugin_name
            and isinstance(version, str)
            and version
        ):
            msg1 = "descriptor-identity"
            msg2 = "descriptor metadata must include namespace, name, and version"
            raise PluginArtifactValidationError(msg1, msg2)

        existing = await self._installed_for(namespace, plugin_name)
        if existing is not None:
            if existing.artifact_digest == expectation.artifact_digest:
                return existing
            raise PluginVersionConflictError(namespace, plugin_name, existing.version)

        actions, triggers = summarize_targets(validation.descriptor)
        installed = InstalledPlugin(
            name=f"{namespace}/{plugin_name}",
            description=metadata.get("description"),
            namespace=namespace,
            plugin_name=plugin_name,
            version=version,
            display_name=metadata.get("displayName"),
            artifact_repository=expectation.repository,
            artifact_digest=expectation.artifact_digest,
            catalog_source_id=None,
            status=PluginInstallStatus.INSTALLED,
            descriptor=validation.descriptor,
            documentation=validation.documentation,
            actions=actions,
            triggers=triggers,
            validation_report=validation.report,
            installed_at=datetime.now(UTC),
            created_by=self.user.id,
            updated_by=self.user.id,
            labels={},
        )
        self.session.add(installed)
        await self.session.commit()
        await self.session.refresh(installed)
        logger.info(
            "plugin installed",
            namespace=installed.namespace,
            name=installed.plugin_name,
            version=installed.version,
            digest=installed.artifact_digest,
            source=expectation.repository,
        )
        return installed

    async def uninstall_plugin(self, installed_id: UUID) -> None:
        """Remove one installed plugin record."""
        installed = await self.get_installed_plugin(installed_id)
        await self.session.delete(installed)
        await self.session.commit()
        logger.info(
            "plugin uninstalled",
            namespace=installed.namespace,
            name=installed.plugin_name,
            version=installed.version,
        )

    async def get_installed_plugin(self, installed_id: UUID) -> InstalledPlugin:
        """Return one installed plugin by ID."""
        installed = await self.session.get(InstalledPlugin, installed_id)
        if installed is None:
            msg = "Installed plugin"
            raise PluginNotFoundError(msg, installed_id)
        return installed

    async def list_installed_plugins(
        self,
        *,
        limit: int,
        cursor: str | None,
        sort: str | None,
        query_params_items: Iterable[tuple[str, str]],
        include_total: bool,
    ) -> InstalledPluginListResponse:
        """List installed plugins with the shared filtering/sorting pipeline."""
        return await self.list_resources(
            model=InstalledPlugin,
            response_type=InstalledPluginListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=query_params_items,
            include_total=include_total,
        )

    # ------------------------------------------------------------------
    # Validation pipeline
    # ------------------------------------------------------------------

    async def _run_pipeline(self, client: ArtifactReader, expectation: ArtifactExpectation) -> ArtifactValidationResult:
        """Run the full artifact validation pipeline.

        Raises PluginArtifactValidationError on the first failed check; all
        checks that passed before the failure are described in the message.
        """
        result = ArtifactValidationResult()
        manifest, manifest_digest = await self._fetch_manifest(client, expectation, result)
        self._verify_manifest_envelope(manifest, manifest_digest, expectation, result)
        config = await self._fetch_config(client, expectation, manifest, result)
        descriptor = await self._fetch_descriptor(client, expectation, manifest, config, result)
        content_bundle = await self._fetch_content_bundle(client, expectation, manifest, result)
        self._verify_documentation(descriptor, content_bundle, expectation, result)
        self._extract_implementations(descriptor, content_bundle, result)
        return result

    async def _fetch_manifest(
        self,
        client: ArtifactReader,
        expectation: ArtifactExpectation,
        result: ArtifactValidationResult,
    ) -> tuple[dict[str, Any], str]:
        """Read the artifact manifest by its immutable digest reference."""
        try:
            manifest, manifest_digest, _ = await client.get_manifest(
                expectation.repository, expectation.artifact_digest
            )
        except Exception as error:
            msg = "artifact-fetch"
            raise PluginArtifactValidationError(msg, str(getattr(error, "message", error))) from error
        result.record("artifact-fetch", f"read {expectation.repository}@{expectation.artifact_digest}")
        return manifest, manifest_digest

    def _verify_manifest_envelope(
        self,
        manifest: dict[str, Any],
        manifest_digest: str,
        expectation: ArtifactExpectation,
        result: ArtifactValidationResult,
    ) -> None:
        """Verify the artifact type and digest immutability of the manifest."""
        if manifest.get("artifactType") != PLUGIN_ARTIFACT_TYPE:
            msg1 = "artifact-type"
            msg2 = f"artifactType is {manifest.get('artifactType')!r}"
            raise PluginArtifactValidationError(msg1, msg2)
        if manifest_digest != expectation.artifact_digest:
            msg1 = "manifest-digest"
            msg2 = f"read {manifest_digest} for reference {expectation.artifact_digest}"
            raise PluginArtifactValidationError(msg1, msg2)
        result.record("artifact-type", "artifact is a Syntara plugin metadata artifact")
        result.record("manifest-digest", "manifest digest matches the artifact reference")

    async def _fetch_config(
        self,
        client: ArtifactReader,
        expectation: ArtifactExpectation,
        manifest: dict[str, Any],
        result: ArtifactValidationResult,
    ) -> dict[str, Any]:
        """Read and verify the artifact config blob."""
        config_descriptor = manifest.get("config")
        if not isinstance(config_descriptor, dict):
            msg1 = "config"
            msg2 = "manifest config descriptor is missing"
            raise PluginArtifactValidationError(msg1, msg2)
        if descriptor_media_type(config_descriptor) != PLUGIN_CONFIG_MEDIA_TYPE:
            msg1 = "config-media-type"
            msg2 = f"config mediaType is {config_descriptor.get('mediaType')!r}"
            raise PluginArtifactValidationError(msg1, msg2)
        try:
            config_content = await client.get_blob(expectation.repository, descriptor_digest(config_descriptor))
        except Exception as error:
            msg = "config-fetch"
            raise PluginArtifactValidationError(msg, str(getattr(error, "message", error))) from error
        result.record("config", "config blob read and media type verified")
        return parse_json(config_content, "plugin artifact config")

    async def _fetch_descriptor(
        self,
        client: ArtifactReader,
        expectation: ArtifactExpectation,
        manifest: dict[str, Any],
        config: dict[str, Any],
        result: ArtifactValidationResult,
    ) -> dict[str, Any]:
        """Read the descriptor layer and verify its digest binding and identity."""
        manifest_layer = find_layer_by_media_type(manifest, PLUGIN_MANIFEST_MEDIA_TYPE)
        if manifest_layer is None:
            msg1 = "descriptor-layer"
            msg2 = "manifest has no plugin.manifest.yaml layer"
            raise PluginArtifactValidationError(msg1, msg2)
        try:
            descriptor_content = await client.get_blob(expectation.repository, descriptor_digest(manifest_layer))
        except Exception as error:
            msg = "descriptor-fetch"
            raise PluginArtifactValidationError(msg, str(getattr(error, "message", error))) from error
        descriptor = parse_json(descriptor_content, "plugin descriptor")
        result.record("descriptor-digest", "plugin descriptor layer read and hash-verified")
        self._verify_descriptor_binding(descriptor_content, config, result)
        self._verify_descriptor_identity(descriptor, expectation, result)
        result.descriptor = descriptor
        return descriptor

    def _verify_descriptor_binding(
        self,
        descriptor_content: bytes,
        config: dict[str, Any],
        result: ArtifactValidationResult,
    ) -> None:
        """Verify the descriptor digest recorded in the artifact config."""
        config_descriptor_digest = config.get("pluginDescriptorDigest")
        if not isinstance(config_descriptor_digest, str) or not config_descriptor_digest:
            return
        actual = f"sha256:{sha256(descriptor_content).hexdigest()}"
        if actual != config_descriptor_digest:
            msg1 = "descriptor-config-binding"
            msg2 = f"descriptor digest {actual} does not match config {config_descriptor_digest}"
            raise PluginArtifactValidationError(msg1, msg2)
        result.record("descriptor-config-binding", "descriptor digest matches the artifact config")

    def _verify_descriptor_identity(
        self,
        descriptor: dict[str, Any],
        expectation: ArtifactExpectation,
        result: ArtifactValidationResult,
    ) -> None:
        """Verify the descriptor identity matches the expected identity.

        Expected fields that are ``None`` (uploads without manifest
        annotations) are skipped; the descriptor kind is always checked.
        """
        metadata = descriptor.get("metadata")
        if not isinstance(metadata, dict):
            msg1 = "descriptor-metadata"
            msg2 = "descriptor has no metadata"
            raise PluginArtifactValidationError(msg1, msg2)
        identity_mismatches = [
            f"{field_name} is {value!r}, expected {expected!r}"
            for field_name, value, expected in (
                ("kind", descriptor.get("kind"), "PluginDescriptor"),
                ("namespace", metadata.get("namespace"), expectation.namespace),
                ("name", metadata.get("name"), expectation.plugin_name),
                ("version", metadata.get("version"), expectation.version),
            )
            if expected is not None and value != expected
        ]
        if identity_mismatches:
            msg = "descriptor-identity"
            raise PluginArtifactValidationError(msg, "; ".join(identity_mismatches))
        result.record("descriptor-identity", "descriptor identity matches the artifact metadata")

    def _extract_implementations(
        self,
        descriptor: dict[str, Any],
        content_bundle: bytes,
        result: ArtifactValidationResult,
    ) -> None:
        """Extract implementation source code from the content bundle.

        For each target whose runtime declares an ``implementation`` path,
        the file is read from the content bundle and its source stored in
        the action summary so the executor can run real plugin code.
        """
        targets = descriptor.get("spec", {}).get("targets", [])
        if not isinstance(targets, list):
            return
        extracted = 0
        for target in targets:
            if not isinstance(target, dict):
                continue
            runtime = target.get("runtime", {})
            if not isinstance(runtime, dict):
                continue
            impl_path = runtime.get("implementation")
            if not isinstance(impl_path, str) or not impl_path:
                continue
            source = extract_file(content_bundle, impl_path)
            if source is None:
                msg1 = "implementation"
                msg2 = f"implementation file {impl_path!r} missing from content bundle"
                raise PluginArtifactValidationError(msg1, msg2)
            runtime["implementation_source"] = source.decode("utf-8")
            extracted += 1
        if extracted > 0:
            result.record(
                "implementation",
                f"extracted {extracted} implementation file(s) from the content bundle",
            )
        custom_runner = sum(
            1
            for target in targets
            if isinstance(target, dict)
            and isinstance(target.get("runtime"), dict)
            and target["runtime"].get("kind") == "custom-runner"
        )
        if custom_runner > 0:
            result.record(
                "custom-runner",
                f"registered {custom_runner} custom-runner action(s) for Execution Plane dispatch",
            )

    async def _fetch_content_bundle(
        self,
        client: ArtifactReader,
        expectation: ArtifactExpectation,
        manifest: dict[str, Any],
        result: ArtifactValidationResult,
    ) -> bytes:
        """Read and verify the content-bundle layer."""
        content_layer = find_layer_by_media_type(manifest, PLUGIN_CONTENT_MEDIA_TYPE)
        if content_layer is None:
            msg1 = "content-bundle"
            msg2 = "manifest has no content.tar.gz layer"
            raise PluginArtifactValidationError(msg1, msg2)
        try:
            content_bundle = await client.get_blob(expectation.repository, descriptor_digest(content_layer))
        except Exception as error:
            msg = "content-fetch"
            raise PluginArtifactValidationError(msg, str(getattr(error, "message", error))) from error
        result.record("content-bundle", "content bundle read and hash-verified")
        return content_bundle

    def _verify_documentation(
        self,
        descriptor: dict[str, Any],
        content_bundle: bytes,
        expectation: ArtifactExpectation,
        result: ArtifactValidationResult,
    ) -> None:
        """Extract the documentation file and verify its digest."""
        doc_path = documentation_path(descriptor)
        if doc_path is None:
            return
        doc_bytes = extract_file(content_bundle, doc_path)
        if doc_bytes is None:
            msg1 = "documentation"
            msg2 = f"documentation file {doc_path!r} missing from bundle"
            raise PluginArtifactValidationError(msg1, msg2)
        expected_doc_digest = self._expected_documentation_digest(descriptor, expectation)
        actual_doc_digest = f"sha256:{sha256(doc_bytes).hexdigest()}"
        if expected_doc_digest and actual_doc_digest != expected_doc_digest:
            msg = "documentation-digest"
            detail = f"documentation digest {actual_doc_digest} does not match {expected_doc_digest}"
            raise PluginArtifactValidationError(msg, detail)
        if expected_doc_digest:
            result.record("documentation-digest", f"documentation {doc_path!r} digest verified")
        result.record("documentation", f"documentation {doc_path!r} extracted from bundle")
        result.documentation = doc_bytes.decode("utf-8")

    @staticmethod
    def _expected_documentation_digest(descriptor: dict[str, Any], expectation: ArtifactExpectation) -> str | None:
        """Return the digest the documentation is expected to hash to."""
        if expectation.documentation_digest:
            return expectation.documentation_digest
        spec = descriptor.get("spec")
        documentation = spec.get("documentation") if isinstance(spec, dict) else None
        if isinstance(documentation, dict):
            digest = documentation.get("digest")
            if isinstance(digest, str) and digest:
                return digest
        return None
