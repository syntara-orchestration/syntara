"""Shared fixtures for all integration tests.

Provides Rego mocking so that integration tests outside ``tests/integration/api/``
(which has its own richer Rego mock using the CLI) can still run without an Rego
server.

Overrides ``test_db_session`` to use real commits (not rollback-based
isolation) because integration tests often create data that must be visible
across multiple database connections (e.g. API clients, concurrent sessions).
"""

import asyncio
import contextlib
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import boto3
import pytest
import pytest_asyncio
import sqlalchemy
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from uvicorn import Config, Server

from syntara.authz.engine import clear_authz_cache, init_authz_cache
from syntara.authz.models.project import Project
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.models.group import Group
from syntara.core.websocket.router import build_websocket_router

pytest_plugins = [
    "tests.integration.fixtures.database",
    "tests.integration.fixtures.client",
    "tests.integration.fixtures.groups",
    "tests.integration.fixtures.temporal",
    "tests.integration.fixtures.workflows",
    "tests.integration.fixtures.factories",
    "tests.integration.fixtures.jwt",
    "tests.integration.fixtures.mocks",
    "tests.integration.fixtures.settings",
    "tests.integration.fixtures.tools",
    "tests.integration.fixtures.users",
]

_MOTO_BUCKET = "nexus-integration-test"
_MOTO_REGION = "us-east-1"


@pytest_asyncio.fixture(scope="session")
async def test_db_template(
    test_db_engine: AsyncEngine, test_db_admin_url: URL
) -> AsyncGenerator[tuple[URL, str, str, AsyncEngine], None]:
    """Snapshot the post-seeding database as a PostgreSQL template.

    Calls run_seeders() directly (same seeders that session_app runs) so the
    template contains runtime_settings, installation, and setting_categories
    data.  Each test restore returns to this seeded state instead of an empty
    post-migration state.  NullPool guarantees all connections are closed before
    CREATE DATABASE … TEMPLATE (which requires zero active sessions on the
    source database).

    Yields:
        (admin_url, db_name, template_name) used by _restore_from_template.

    """
    from syntara.core.seed import run_seeders

    seeder_factory = async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
    await run_seeders(seeder_factory)

    # run_seeders also populates users, workflows, groups, etc.  Those must NOT be
    # in the template because tests seed their own per-test data and assume an empty
    # DB.  Truncate the same tables the old TRUNCATE-based cleanup truncated, leaving
    # only the four tables that were previously excluded from truncation.
    preserved = frozenset({"alembic_version", "installation", "runtime_settings", "setting_categories"})
    preparer = test_db_engine.dialect.identifier_preparer
    async with test_db_engine.begin() as conn:
        result = await conn.execute(
            sqlalchemy.text(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('information_schema', 'pg_catalog') "
                "ORDER BY table_schema, table_name"
            )
        )
        to_truncate = [
            f"{preparer.quote_schema(s)}.{preparer.quote(t)}" if s and s != "public" else preparer.quote(t)
            for s, t in result
            if t not in preserved
        ]
    if to_truncate:
        async with test_db_engine.begin() as conn:
            await conn.execute(sqlalchemy.text(f"TRUNCATE {', '.join(to_truncate)} RESTART IDENTITY CASCADE"))

    db_name = test_db_engine.url.database or "test"
    template_name = f"{db_name}_tpl"

    admin_engine = create_async_engine(test_db_admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(
                sqlalchemy.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid != pg_backend_pid()"
                ).bindparams(db=db_name)
            )
            await conn.execute(sqlalchemy.text(f'CREATE DATABASE "{template_name}" TEMPLATE "{db_name}"'))
        yield test_db_admin_url, db_name, template_name, admin_engine
    finally:
        async with admin_engine.connect() as conn:
            await conn.execute(
                sqlalchemy.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid != pg_backend_pid()"
                ).bindparams(db=template_name)
            )
            await conn.execute(sqlalchemy.text(f'DROP DATABASE IF EXISTS "{template_name}"'))
        await admin_engine.dispose()


async def _restore_from_template(admin_engine: AsyncEngine, db_name: str, template_name: str) -> None:
    """Reset the test database to the clean post-migration snapshot.

    Uses PostgreSQL's template-database mechanism (filesystem-level copy)
    instead of per-table TRUNCATE.  pg_terminate_backend evicts any stray
    connections before the DROP so it never blocks.
    """
    async with admin_engine.connect() as conn:
        await conn.execute(
            sqlalchemy.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :db AND pid != pg_backend_pid()"
            ).bindparams(db=db_name)
        )
        await conn.execute(sqlalchemy.text(f'DROP DATABASE "{db_name}"'))
        await conn.execute(sqlalchemy.text(f'CREATE DATABASE "{db_name}" TEMPLATE "{template_name}"'))


@pytest_asyncio.fixture
async def test_db_session_factory(test_db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory from the test database engine."""
    return async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def test_db_session(
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_db_template: tuple[URL, str, str, AsyncEngine],
) -> AsyncGenerator[AsyncSession, None]:
    """Integration test database session with template-based per-test isolation.

    Restores the database to the clean post-migration snapshot before each
    test instead of issuing a TRUNCATE.  This is faster because PostgreSQL
    copies the data directory at the filesystem level rather than walking
    every table's rows and WAL-logging their deletion.
    """
    _admin_url, db_name, template_name, admin_engine = test_db_template
    await _restore_from_template(admin_engine, db_name, template_name)

    session = test_db_session_factory()
    try:
        yield session
        if session.is_active:
            await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@pytest_asyncio.fixture
async def test_project_id(test_db_session: AsyncSession) -> UUID:
    """Create a test project and return its ID.

    Provides a non-builtin project for tests that create project-scoped resources.
    """
    project = Project(name=f"test-project-{uuid4().hex[:8]}", description="Test project")
    test_db_session.add(project)
    await test_db_session.flush()
    await test_db_session.refresh(project)
    return project.id


@pytest_asyncio.fixture(autouse=True)
async def _seed_authenticated_group(test_db_session: AsyncSession) -> None:
    """Ensure the built-in authenticated group exists for every integration test."""
    result = await test_db_session.exec(
        select(Group).where(Group.name == AUTHENTICATED_GROUP_NAME, Group.deleted_at.is_(None))  # type: ignore[union-attr]
    )
    if not result.first():
        test_db_session.add(Group(id=uuid4(), name=AUTHENTICATED_GROUP_NAME, is_builtin=True, labels={}))
        await test_db_session.flush()


@pytest_asyncio.fixture
async def _seed_integration_data(test_db_session: AsyncSession) -> None:
    """Seed authz and builtin workflow data.

    Not autouse — directories opt in via autouse wrapper fixtures in subdirectory conftest files.
    This avoids inflating workflow/resource counts in pagination and telemetry tests.
    """
    from syntara.authz.seed import seed_authz_data
    from syntara.workflows.seed_builtin import seed_builtin_workflows

    await seed_authz_data(test_db_session)
    await seed_builtin_workflows(test_db_session)


@pytest.fixture(autouse=True)
def _reset_opa_cache() -> Generator[None, None, None]:
    """Reset Rego cache between integration tests."""
    init_authz_cache(enabled=True, ttl_seconds=300)
    yield
    clear_authz_cache()


@pytest.fixture(autouse=True)
def _mock_evaluator_allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace authz evaluator with one that always allows requests.

    This is a lightweight fallback for integration tests that don't live
    under ``tests/integration/api/`` (those use the CLI-based mock).
    The ``api`` conftest's ``_mock_evaluator`` fixture overrides this one for
    tests in that directory because pytest uses the most-specific conftest.
    """
    from syntara.api.main import app
    from syntara.authz.dependencies import get_authz_evaluator

    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate = MagicMock(
        return_value={
            "allow": True,
            "deny": False,
            "matched_policy": "test-allow-all",
            "allowed_projects": ["*"],
        }
    )

    def _mock_getter(request: Any = None) -> AsyncMock:  # noqa: ANN401
        return mock_evaluator

    monkeypatch.setattr("syntara.authz.dependencies.get_authz_evaluator", _mock_getter)
    monkeypatch.setattr("syntara.authz.dependencies.get_authz_evaluator", _mock_getter)
    monkeypatch.setattr("syntara.workflows.executions_router.get_authz_evaluator", _mock_getter)

    app.dependency_overrides[get_authz_evaluator] = lambda: mock_evaluator


@pytest.fixture
def websocket_example_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[Path, FastAPI], None, None]:
    """Create a test application and return FastAPI app.

    Returns:
        Tuple of (project_root, configured FastAPI app)

    """
    # Create directory structure
    project_root = tmp_path / "project"
    nexus_dir = project_root / "src" / "syntara"
    core_dir = nexus_dir / "core" / "websocket"
    core_dir.mkdir(parents=True)

    component_dir = nexus_dir / "testcomp"
    ws_dir = component_dir / "ws"
    ws_dir.mkdir(parents=True)

    schemas_dir = nexus_dir / "schemas" / "testcomp"
    schemas_dir.mkdir(parents=True)

    # Create __init__.py files
    (nexus_dir / "__init__.py").touch()
    (component_dir / "__init__.py").touch()
    (ws_dir / "__init__.py").touch()
    (core_dir / "__init__.py").touch()

    # Create handlers.py
    handlers1_content = '''"""Handler file."""
from datetime import datetime, timezone
from typing import Any


async def handle_chat(message: dict[str, Any], connection_id: str) -> dict[str, Any]:
    """Handle chat messages - returns uppercase."""
    return {
        "reply": message["message"].upper(),
        "type": "echo",
        "handler": "handlers1",
    }


async def handle_coffee(message: dict[str, Any], connection_id: str) -> dict[str, Any]:
    """Handle coffee requests - returns coffee word."""
    return {
        "output": "espresso",
        "handler": "handlers1",
    }
'''
    (ws_dir / "handlers1.py").write_text(handlers1_content)

    handlers2_content = '''"""Handler file."""
import asyncio
from datetime import datetime, timezone
from typing import Any
from starlette.websockets import WebSocket


async def handle_events(message: dict[str, Any], connection_id: str) -> dict[str, Any]:
    """Handle event subscription requests."""
    return {
        "status": "subscribed",
        "group": message["group"],
        "handler": "handlers2",
    }


async def on_connect_tokens(websocket: WebSocket, connection_id: str) -> None:
    """Send tokens on connection for receive-only channel testing."""
    # Send 5 tokens with sequence numbers
    for i in range(5):
        token_event = {
            "token": f"token_{i}",
            "sequence": i,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await websocket.send_json(token_event)
        # Small delay to ensure messages are sent sequentially
        await asyncio.sleep(0.01)
'''
    (ws_dir / "handlers2.py").write_text(handlers2_content)

    # Create AsyncAPI specs
    handlers1_spec = """---
asyncapi: 3.0.0
info:
  title: Example Component WebSocket API
  version: 1.0.0
  description: |
    Example WebSocket component demonstrating multiple channels.

servers:
  development:
    host: localhost:8000
    protocol: ws
    description: Local development server
  production:
    host: api.automation.example.com
    protocol: wss
    description: Production server with TLS

channels:
  coffee:
    address: /ws/testcomp/v1/coffee
    description: |
      Coffee word generator endpoint that receives input text and
      responds with coffee-related words.

      For each character in the input, the server returns a different
      coffee-related word.
      Example: input="hi" returns "espresso hario"

      Connection lifecycle:
      1. Client initiates WebSocket handshake to /ws/testcomp/v1/coffee
      2. Server accepts connection
      3. Client sends CoffeeRequest message with input text
      4. Server responds with CoffeeResponse containing
         space-separated coffee words
      5. Connection remains open for additional requests
      6. Either party can close the connection

    messages:
      coffeeRequest:
        $ref: '#/components/messages/CoffeeRequest'
      coffeeResponse:
        $ref: '#/components/messages/CoffeeResponse'
      errorResponse:
        $ref: '#/components/messages/ErrorResponse'

  chat:
    address: /ws/testcomp/v1/chat
    description: |
      Bidirectional chat endpoint with server-initiated messages.

      Features:
      - Server sends random messages to client every 3 seconds
      - Client can send messages and receives uppercase echo responses

      Connection lifecycle:
      1. Client initiates WebSocket handshake to /ws/testcomp/v1/chat
      2. Server accepts connection and starts sending random messages
      3. Client can send ChatRequest with message text at any time
      4. Server responds with ChatResponse containing uppercase message
      5. Server continues sending random messages every 3 seconds
      6. Either party can close the connection

    messages:
      chatRequest:
        $ref: '#/components/messages/ChatRequest'
      chatResponse:
        $ref: '#/components/messages/ChatResponse'
      errorResponse:
        $ref: '#/components/messages/ErrorResponse'

operations:
  sendCoffeeRequest:
    action: send
    channel:
      $ref: '#/channels/coffee'
    summary: Send a coffee request with input text
    description: |
      Client sends input text to receive coffee-related words for
      each character
    messages:
      - $ref: '#/channels/coffee/messages/coffeeRequest'

  receiveCoffeeResponse:
    action: receive
    channel:
      $ref: '#/channels/coffee'
    summary: Receive a coffee response
    description: |
      Server responds with space-separated coffee words corresponding
      to each input character
    messages:
      - $ref: '#/channels/coffee/messages/coffeeResponse'
      - $ref: '#/channels/coffee/messages/errorResponse'

  sendChatRequest:
    action: send
    channel:
      $ref: '#/channels/chat'
    summary: Send a chat message
    description: |
      Client sends a chat message and receives an uppercase echo response
    messages:
      - $ref: '#/channels/chat/messages/chatRequest'

  receiveChatResponse:
    action: receive
    channel:
      $ref: '#/channels/chat'
    summary: Receive chat responses and random messages
    description: |
      Server responds with uppercase echo of client messages and
      periodically sends random messages every 3 seconds
    messages:
      - $ref: '#/channels/chat/messages/chatResponse'
      - $ref: '#/channels/chat/messages/errorResponse'

components:
  messages:
    CoffeeRequest:
      name: CoffeeRequest
      title: Coffee Request
      summary: Request message containing input text for coffee word generation
      contentType: application/json
      payload:
        type: object
        required:
          - input
        properties:
          input:
            type: string
            description: The input text to convert to coffee words
            minLength: 1
            maxLength: 100
            example: hi
      examples:
        - name: SimpleInput
          summary: A simple coffee request
          payload:
            input: hi
        - name: LongerInput
          summary: A longer coffee request
          payload:
            input: coffee

    CoffeeResponse:
      name: CoffeeResponse
      title: Coffee Response
      summary: Response message containing coffee-related words
      contentType: application/json
      payload:
        type: object
        required:
          - output
        properties:
          output:
            type: string
            description: |
              Space-separated coffee words corresponding to each
              input character
            example: espresso hario
          timestamp:
            type: string
            format: date-time
            description: |
              ISO 8601 timestamp when the response was generated
              (UTC)
            example: '2025-10-23T10:30:00.000Z'
      examples:
        - name: SimpleCoffeeResponse
          summary: Response to a simple coffee request (input="hi")
          payload:
            output: espresso hario
            timestamp: '2025-10-23T10:30:00.000Z'
        - name: LongerCoffeeResponse
          summary: Response to a longer coffee request (input="coffee")
          payload:
            output: cappuccino origin filter filter extraction extraction
            timestamp: '2025-10-23T10:30:00.000Z'

    ChatRequest:
      name: ChatRequest
      title: Chat Request
      summary: Request message containing chat text
      contentType: application/json
      payload:
        type: object
        required:
          - message
        properties:
          message:
            type: string
            description: The chat message to send
            minLength: 1
            maxLength: 1000
            example: Hello there
      examples:
        - name: SimpleMessage
          summary: A simple chat message
          payload:
            message: Hello there
        - name: LongerMessage
          summary: A longer chat message
          payload:
            message: How are you doing today?

    ChatResponse:
      name: ChatResponse
      title: Chat Response
      summary: Response message containing chat reply
      contentType: application/json
      payload:
        type: object
        required:
          - reply
          - type
        properties:
          reply:
            type: string
            description: |
              The chat reply - either uppercase echo of client message
              or a random server message
            example: HELLO THERE
          type:
            type: string
            description: Type of message - 'echo' for client echo or 'random' for server-initiated
            enum:
              - echo
              - random
            example: echo
          timestamp:
            type: string
            format: date-time
            description: |
              ISO 8601 timestamp when the response was generated
              (UTC)
            example: '2025-10-23T10:30:00.000Z'
      examples:
        - name: EchoResponse
          summary: Response echoing client message in uppercase
          payload:
            reply: HELLO THERE
            type: echo
            timestamp: '2025-10-23T10:30:00.000Z'
        - name: RandomMessage
          summary: Random server-initiated message
          payload:
            reply: How's your day going?
            type: random
            timestamp: '2025-10-23T10:30:00.000Z'

    ErrorResponse:
      name: ErrorResponse
      title: Error Response
      summary: Error message for invalid requests
      contentType: application/json
      payload:
        type: object
        required:
          - error
          - message
        properties:
          error:
            type: string
            description: Error type identifier
            enum:
              - INVALID_REQUEST
              - VALIDATION_ERROR
              - INTERNAL_ERROR
            example: VALIDATION_ERROR
          message:
            type: string
            description: Human-readable error message
            example: Name field is required
          timestamp:
            type: string
            format: date-time
            description: ISO 8601 timestamp when the error occurred (UTC)
            example: '2025-10-23T10:30:00.000Z'
      examples:
        - name: ValidationError
          summary: Error when input is missing
          payload:
            error: VALIDATION_ERROR
            message: Input field is required
            timestamp: '2025-10-23T10:30:00.000Z'
        - name: InvalidRequest
          summary: Error when request format is invalid
          payload:
            error: INVALID_REQUEST
            message: Invalid JSON format
            timestamp: '2025-10-23T10:30:00.000Z'
"""
    (schemas_dir / "websocket-handlers1.yaml").write_text(handlers1_spec)

    handlers2_spec = """---
asyncapi: 3.0.0
info:
  title: Example Component WebSocket API
  version: 1.0.0
  description: |
    Example WebSocket component demonstrating multiple channels.

servers:
  development:
    host: localhost:8000
    protocol: ws
    description: Local development server
  production:
    host: api.automation.example.com
    protocol: wss
    description: Production server with TLS

channels:

  events:
    address: /ws/testcomp/v1/events
    messages:
      eventsRequest:
        $ref: '#/components/messages/EventsRequest'
      eventsResponse:
        $ref: '#/components/messages/EventsResponse'

  tokens:
    address: /ws/testcomp/v1/tokens
    description: |
      Receive-only token streaming endpoint for integration testing.

      This channel demonstrates receive-only functionality where the server
      sends tokens to clients without requiring any client messages.

      Features:
      - Server sends periodic token events via on_connect handler
      - No Request message required (receive-only)
      - No handle_tokens function required (receive-only)
      - Connection stays alive until client disconnects

      Connection lifecycle:
      1. Client initiates WebSocket handshake to /ws/testcomp/v1/tokens
      2. Server accepts connection
      3. Server begins sending Token messages immediately via on_connect
      4. Client receives tokens without sending any requests
      5. Either party can close the connection

    messages:
      token:
        $ref: '#/components/messages/Token'

operations:

  receiveTokens:
    action: receive
    channel:
      $ref: '#/channels/tokens'
    summary: Receive periodic token events
    description: |
      Server sends token events at regular intervals without requiring
      any client messages. This is a receive-only operation demonstrating
      server-push functionality.
    messages:
      - $ref: '#/channels/tokens/messages/token'

  sendEventsRequest:
    action: send
    channel:
      $ref: '#/channels/events'
    messages:
      - $ref: '#/channels/events/messages/eventsRequest'

  receiveEventsResponse:
    action: receive
    channel:
      $ref: '#/channels/events'
    messages:
      - $ref: '#/channels/events/messages/eventsResponse'

components:
  messages:
    EventsRequest:
      contentType: application/json
      payload:
        type: object
        required:
          - group
        properties:
          group:
            type: string
    EventsResponse:
      contentType: application/json
      payload:
        type: object
        required:
          - status
          - group
        properties:
          status:
            type: string
          group:
            type: string
          handler:
            type: string
    Token:
      name: Token
      title: Token
      summary: Token event message for receive-only channel testing
      contentType: application/json
      payload:
        type: object
        required:
          - token
          - sequence
        properties:
          token:
            type: string
            description: The token value
            example: token_0
          sequence:
            type: integer
            description: Sequential number of this token
            minimum: 0
            example: 0
          timestamp:
            type: string
            format: date-time
            description: ISO 8601 timestamp when the token was generated (UTC)
            example: '2025-12-01T10:30:00.000Z'
      examples:
        - name: FirstToken
          summary: First token in sequence
          payload:
            token: token_0
            sequence: 0
            timestamp: '2025-12-01T10:30:00.000Z'
        - name: SecondToken
          summary: Second token in sequence
          payload:
            token: token_1
            sequence: 1
            timestamp: '2025-12-01T10:30:01.000Z'
"""
    (schemas_dir / "websocket-handlers2.yaml").write_text(handlers2_spec)

    # Add project to Python path
    sys.path.insert(0, str(nexus_dir.parent))

    # Mock __file__ to point to our temporary structure
    fake_endpoint_factory = core_dir / "endpoint_factory.py"
    fake_endpoint_factory.touch()
    monkeypatch.setattr(
        "syntara.core.websocket.endpoint_factory.__file__",
        str(fake_endpoint_factory),
    )

    # Mock importlib.resources.files to return our temp schemas directory
    def mock_files(package: str) -> Path:
        if package == "syntara":
            return nexus_dir
        msg = f"Package {package} not found"
        raise FileNotFoundError(msg)

    monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", mock_files)

    # Create FastAPI app
    app = FastAPI()
    router = build_websocket_router()
    app.include_router(router)

    yield project_root, app

    # Cleanup
    sys.path.remove(str(nexus_dir.parent))


async def _wait_for_server(host: str, port: int) -> None:
    """Poll until the server is accepting TCP connections."""
    async with asyncio.timeout(10.0):
        while True:
            try:
                _, writer = await asyncio.open_connection(host, port)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.1)


@pytest_asyncio.fixture
async def example_app_server(websocket_example_app: tuple[Path, FastAPI]) -> AsyncGenerator[tuple[Path, FastAPI], None]:
    """Create Server with Websocket example channels."""
    project_root, app = websocket_example_app
    config = Config(app, host="127.0.0.1", port=9999, log_level="error")
    server = Server(config)

    async def _serve_without_sys_exit() -> None:
        """Wrap server.serve() to convert SystemExit into a normal exception.

        Uvicorn calls sys.exit(1) on port conflicts. asyncio re-raises
        SystemExit from tasks immediately (bypassing except Exception blocks),
        which breaks fixture teardown and cascades failures to subsequent tests.
        """
        try:
            await server.serve()
        except SystemExit as exc:
            msg = f"uvicorn exited with code {exc.code}"
            raise RuntimeError(msg) from exc

    server_task = asyncio.create_task(_serve_without_sys_exit())

    try:
        await _wait_for_server("127.0.0.1", 9999)
    except (TimeoutError, OSError):
        if server_task.done() and not server_task.cancelled():
            try:
                server_task.result()
            except Exception as exc:
                pytest.fail(f"Server failed to start: {exc}")
        server_task.cancel()
        with contextlib.suppress(BaseException):
            await server_task
        pytest.fail("Server failed to start within timeout")

    yield project_root, app

    # Shutdown server gracefully
    server.should_exit = True
    try:
        await asyncio.wait_for(server_task, timeout=5.0)
    except (TimeoutError, Exception):
        if not server_task.done():
            server_task.cancel()
        with contextlib.suppress(BaseException):
            await server_task


@pytest.fixture(autouse=True)
def _moto_s3() -> Generator[None, None, None]:
    """Provide a moto-backed S3 retriever for all integration tests.

    Creates a real S3FileRetriever backed by moto's mock_aws, then injects
    it into the FileManager singleton. This avoids endpoint_url conflicts
    between moto interception and custom S3 endpoints.
    """
    with mock_aws():
        conn = boto3.client("s3", region_name=_MOTO_REGION)
        conn.create_bucket(Bucket=_MOTO_BUCKET)

        from syntara.files.file_manager import get_file_manager
        from syntara.files.retrievers.s3 import S3FileRetriever

        retriever = S3FileRetriever(
            endpoint_url=None,
            bucket_name=_MOTO_BUCKET,
            region_name=_MOTO_REGION,
        )

        fm = get_file_manager()
        original_retriever = fm._retriever
        fm._retriever = retriever
        yield
        fm._retriever = original_retriever


@pytest.fixture(autouse=True)
def _skip_ssrf_validation(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Bypass integration SSRF base_url validation for tests using placeholder hostnames.

    Integration configs in tests use non-resolvable hosts (e.g. gateway.example.com), so the
    DNS-resolving SSRF check would reject them. The shared bypass covers every boundary that
    routes through the ``validate_integration_url_no_ssrf`` choke point — write time
    (create/patch) and the runtime resolve/connect paths. Tests that exercise the SSRF check
    itself opt out with ``@pytest.mark.ssrf_enforced``. The probe/patch logic is shared with the
    unit conftest via :mod:`tests.helpers.ssrf_bypass` so the safety-net rules cannot drift.
    """
    from tests.helpers.ssrf_bypass import bypass_integration_ssrf_validation

    if request.node.get_closest_marker("ssrf_enforced"):
        yield
        return

    with bypass_integration_ssrf_validation():
        yield
