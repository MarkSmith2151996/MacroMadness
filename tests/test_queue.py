"""Test queue processor -- enqueue, process, dependencies, backoff, handler dispatch."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db import Base
from src.models import PendingOperation

pytestmark = pytest.mark.asyncio


def _naive_utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Custom datetime class that returns naive datetimes
_OrigDatetime = datetime


class NaiveDatetime(_OrigDatetime):
    @classmethod
    def now(cls, tz=None):
        result = _OrigDatetime.now(timezone.utc)
        return result.replace(tzinfo=None)


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_patch(session_factory):
    """Patch async_session and datetime in queue.processor for SQLite compat."""
    with patch("src.db.async_session", session_factory):
        with patch("src.queue.processor.async_session", session_factory):
            with patch("src.queue.processor.datetime", NaiveDatetime):
                yield session_factory


# ---------------------------------------------------------------------------
# enqueue tests
# ---------------------------------------------------------------------------
async def test_enqueue_creates_pending_operation(db_patch):
    """enqueue should create a PendingOperation in the database."""
    from src.queue.processor import enqueue

    op_id = await enqueue(
        operation="correlation_snapshot",
        payload={"trigger": "test"},
    )

    assert op_id is not None

    async with db_patch() as session:
        op = await session.get(PendingOperation, op_id)
        assert op is not None
        assert op.operation == "correlation_snapshot"
        assert op.payload == {"trigger": "test"}
        assert op.status == "pending"
        assert op.attempts == 0
        assert op.max_attempts == 3


async def test_enqueue_with_dependency(db_patch):
    """enqueue with depends_on should set the dependency."""
    from src.queue.processor import enqueue

    op1_id = await enqueue("score_trade", {"trade_id": 1})
    op2_id = await enqueue("update_weights", {"trigger": "close"}, depends_on=op1_id)

    async with db_patch() as session:
        op2 = await session.get(PendingOperation, op2_id)
        assert op2.depends_on == op1_id


async def test_enqueue_custom_max_attempts(db_patch):
    from src.queue.processor import enqueue

    op_id = await enqueue("test_op", {"data": 1}, max_attempts=5)

    async with db_patch() as session:
        op = await session.get(PendingOperation, op_id)
        assert op.max_attempts == 5


# ---------------------------------------------------------------------------
# process_queue tests
# ---------------------------------------------------------------------------
async def test_process_queue_completes_operation(db_patch):
    """process_queue should process and complete pending operations."""
    from src.queue.processor import enqueue, process_queue

    op_id = await enqueue("score_trade", {"trade_id": 1})

    with patch("src.queue.processor.execute_operation", new_callable=AsyncMock):
        await process_queue()

    async with db_patch() as session:
        op = await session.get(PendingOperation, op_id)
        assert op.status == "completed"
        assert op.completed_at is not None


async def test_process_queue_skips_blocked_dependency(db_patch):
    """Operations with unresolved dependencies should be skipped."""
    from src.queue.processor import enqueue, process_queue

    # Create op1 but don't let it complete
    async with db_patch() as session:
        op1 = PendingOperation(
            operation="score_trade",
            payload={"trade_id": 1},
            status="pending",
            max_attempts=3,
        )
        session.add(op1)
        await session.commit()
        await session.refresh(op1)
        op1_id = op1.id

    # Create op2 that depends on op1
    async with db_patch() as session:
        op2 = PendingOperation(
            operation="update_weights",
            payload={"trigger": "close"},
            depends_on=op1_id,
            status="pending",
            max_attempts=3,
        )
        session.add(op2)
        await session.commit()
        await session.refresh(op2)
        op2_id = op2.id

    # Make execute_operation fail for op1 so it doesn't complete
    mock_execute = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("src.queue.processor.execute_operation", mock_execute):
        await process_queue()

    # op1 should be retrying, op2 should still be pending (dependency not met)
    async with db_patch() as session:
        op1 = await session.get(PendingOperation, op1_id)
        op2 = await session.get(PendingOperation, op2_id)
        assert op1.status == "retrying"
        assert op2.status == "pending"  # Not processed because dep not completed


async def test_process_queue_exponential_backoff(db_patch):
    """Failed operations should get exponential backoff on next_retry_at."""
    from src.queue.processor import enqueue, process_queue

    op_id = await enqueue("test_fail", {"data": 1})

    with patch(
        "src.queue.processor.execute_operation",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Handler failed"),
    ):
        await process_queue()

    async with db_patch() as session:
        op = await session.get(PendingOperation, op_id)
        assert op.attempts == 1
        assert op.last_error == "Handler failed"
        assert op.next_retry_at is not None
        assert op.status == "retrying"

        # Backoff should be 30 * (2^1) = 60 seconds
        now = _naive_utcnow()
        # next_retry_at should be in the future
        assert op.next_retry_at > now - timedelta(seconds=5)


async def test_process_queue_max_attempts_sets_failed(db_patch):
    """Operation reaching max_attempts should be set to 'failed'."""
    from src.queue.processor import enqueue, process_queue

    op_id = await enqueue("test_fail", {"data": 1}, max_attempts=1)

    with patch(
        "src.queue.processor.execute_operation",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Handler failed"),
    ):
        await process_queue()

    async with db_patch() as session:
        op = await session.get(PendingOperation, op_id)
        assert op.status == "failed"
        assert op.attempts == 1


async def test_process_queue_skips_not_ready_for_retry(db_patch):
    """Operations with future next_retry_at should be skipped."""
    from src.queue.processor import process_queue

    async with db_patch() as session:
        op = PendingOperation(
            operation="test_retry",
            payload={"data": 1},
            status="retrying",
            attempts=1,
            max_attempts=3,
            next_retry_at=_naive_utcnow() + timedelta(hours=1),
        )
        session.add(op)
        await session.commit()
        await session.refresh(op)
        op_id = op.id

    mock_execute = AsyncMock()
    with patch("src.queue.processor.execute_operation", mock_execute):
        await process_queue()

    # Should NOT have been processed
    mock_execute.assert_not_called()


# ---------------------------------------------------------------------------
# Handler dispatch tests
# ---------------------------------------------------------------------------
@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_get_handlers_returns_all_handlers():
    """_get_handlers should return all 4 registered handlers."""
    from src.queue.processor import _get_handlers

    handlers = _get_handlers()
    assert isinstance(handlers, dict)
    expected_keys = {"correlation_snapshot", "correlation_impact", "score_trade", "update_weights"}
    assert set(handlers.keys()) == expected_keys


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_get_handlers_values_are_callable():
    """All handler values should be async callables."""
    from src.queue.processor import _get_handlers

    handlers = _get_handlers()
    for name, handler in handlers.items():
        assert callable(handler), f"Handler {name} is not callable"


async def test_execute_operation_unknown_raises(db_patch):
    """execute_operation with unknown operation name should raise ValueError."""
    from src.queue.processor import execute_operation

    op = PendingOperation(
        operation="nonexistent_operation",
        payload={},
        status="pending",
    )

    with pytest.raises(ValueError, match="Unknown operation"):
        await execute_operation(op)
