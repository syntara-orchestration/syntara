"""Transport construction boundary for the standalone event worker."""

from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.lib.encryption import SecretEncryptor
from syntara.core.services.secret_service import SecretService
from syntara.core.services.storage_backend import DatabaseBackend
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_record_runner import KafkaRecordRunner
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.eventstreams.core.deduplication import TerminalDeliveryCache
from syntara.eventstreams.core.runtime import RuntimeFailureCode, SubscriptionRunner, SubscriptionRuntimeError
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.integrations.adapters.kafka import KafkaAdapter
from syntara.integrations.adapters.kafka_credentials import resolve_kafka_authentication
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type
from syntara.integrations.models.integration import Integration
from syntara.integrations.models.integration_configuration import KafkaConfiguration


class ManagedRunnerFactory:
    """Resolve customer secrets in short sessions; never start clients in them."""

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        preparation: EventExecutionPreparationService,
        admission: EventAdmissionService,
        resources: EventWorkerResources,
        encryptor: SecretEncryptor,
        *,
        owner_worker_id: str,
        lookup: TerminalDeliveryCache | None = None,
    ) -> None:
        """Receive process-scoped dependencies; no request or shared session is retained."""
        self._session_factory = session_factory
        self._preparation = preparation
        self._admission = admission
        self._resources = resources
        self._encryptor = encryptor
        self._owner = owner_worker_id
        self._lookup = lookup

    async def __call__(self, snapshot: SubscriptionSnapshot) -> SubscriptionRunner:
        """Return one unstarted transport runner for the exact immutable binding."""
        if snapshot.transport != "kafka" or not isinstance(snapshot.configuration, KafkaSourceConfiguration):
            raise SubscriptionRuntimeError(RuntimeFailureCode.CONFIGURATION_UNAVAILABLE)
        try:
            connection = await self._resolve_connection(snapshot)
        except SQLAlchemyError as exc:
            self._resources.database_failed()
            raise SubscriptionRuntimeError(RuntimeFailureCode.CONNECTION_UNAVAILABLE, transient=True) from exc
        except (OSError, TimeoutError) as exc:
            raise SubscriptionRuntimeError(RuntimeFailureCode.CONNECTION_UNAVAILABLE, transient=True) from exc
        client = KafkaPartitionConsumer(connection, snapshot.configuration, client_id=self._owner)
        return KafkaRecordRunner(
            snapshot,
            client,
            self._session_factory,
            self._preparation,
            self._admission,
            owner_worker_id=self._owner,
            work_semaphore=self._resources.processing,
            lookup=self._lookup,
            gate=self._resources.gate,
        )

    async def _resolve_connection(self, snapshot: SubscriptionSnapshot) -> ResolvedKafkaConnection:
        async with self._session_factory() as session, session.begin():
            secrets = SecretService(session, self._encryptor, DatabaseBackend(session))
            await EventConnectionProvider(session, secret_service=secrets).resolve_revision(snapshot)
            integration = await session.get(Integration, snapshot.integration_id)
            if integration is None or not isinstance(integration.configuration, KafkaConfiguration):
                raise SubscriptionRuntimeError(RuntimeFailureCode.CONFIGURATION_UNAVAILABLE)
            if snapshot.runtime_credential_id is None:
                raise SubscriptionRuntimeError(RuntimeFailureCode.CONFIGURATION_UNAVAILABLE)
            credential, credential_type = await fetch_credential_with_type(session, snapshot.runtime_credential_id)
            decrypted = await secrets.retrieve_secret(credential.secret_id)  # type: ignore[arg-type]
            resolved = InjectorResolver.resolve(credential_type.injectors or {}, decrypted)
            username, password = resolve_kafka_authentication(resolved.extra_vars)
            config = integration.configuration
            connection = ResolvedKafkaConnection(
                bootstrap_servers=list(config.bootstrap_servers),
                security_protocol="SASL_SSL",
                sasl_mechanism=config.sasl_mechanism,
                sasl_plain_username=username,
                sasl_plain_password=password,
                ssl_context=KafkaAdapter(config)._ssl_context(),  # noqa: SLF001 - reuse Integration TLS semantics
            )
        return connection  # noqa: RET504 - session must close before client construction
