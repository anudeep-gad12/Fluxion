"""Tests for ConversationRepo."""

import pytest
from orchestrator.storage.db import Database
from orchestrator.storage.repositories.conversation_repo import ConversationRepo


@pytest.fixture
async def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def repo(db):
    """Create a ConversationRepo with test database."""
    return ConversationRepo(db)


class TestConversationRepo:
    """Tests for ConversationRepo CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_conversation(self, repo):
        """Create a new conversation."""
        result = await repo.create(
            conversation_id="conv-123",
            title="Test Conversation",
            status="active",
        )

        assert result["conversation_id"] == "conv-123"
        assert result["title"] == "Test Conversation"
        assert result["status"] == "active"
        assert "created_at" in result

    @pytest.mark.asyncio
    async def test_create_with_metadata(self, repo):
        """Create conversation with metadata."""
        metadata = {"key": "value", "nested": {"foo": "bar"}}
        result = await repo.create(
            conversation_id="conv-meta",
            metadata=metadata,
        )

        assert result["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_get_existing_conversation(self, repo):
        """Get an existing conversation."""
        await repo.create(conversation_id="conv-get", title="Get Test")

        result = await repo.get("conv-get")

        assert result is not None
        assert result["conversation_id"] == "conv-get"
        assert result["title"] == "Get Test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, repo):
        """Get nonexistent conversation returns None."""
        result = await repo.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_deserializes_metadata(self, repo):
        """Get deserializes JSON metadata."""
        await repo.create(
            conversation_id="conv-json",
            metadata={"test": [1, 2, 3]},
        )

        result = await repo.get("conv-json")

        assert result["metadata"] == {"test": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_list_conversations(self, repo):
        """List returns all conversations."""
        await repo.create(conversation_id="conv-1", title="First")
        await repo.create(conversation_id="conv-2", title="Second")
        await repo.create(conversation_id="conv-3", title="Third")

        result = await repo.list()

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, repo):
        """List filters by status."""
        await repo.create(conversation_id="active-1", status="active")
        await repo.create(conversation_id="archived-1", status="archived")
        await repo.create(conversation_id="active-2", status="active")

        result = await repo.list(status="active")

        assert len(result) == 2
        assert all(c["status"] == "active" for c in result)

    @pytest.mark.asyncio
    async def test_list_with_limit(self, repo):
        """List respects limit."""
        for i in range(10):
            await repo.create(conversation_id=f"conv-{i}")

        result = await repo.list(limit=5)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_list_with_offset(self, repo):
        """List respects offset."""
        for i in range(10):
            await repo.create(conversation_id=f"conv-{i}")

        result = await repo.list(limit=5, offset=5)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_list_ordered_by_created_at_desc(self, repo):
        """List orders by created_at descending (newest first)."""
        await repo.create(conversation_id="oldest")
        await repo.create(conversation_id="middle")
        await repo.create(conversation_id="newest")

        result = await repo.list()

        # Most recent should be first
        assert result[0]["conversation_id"] == "newest"
        assert result[-1]["conversation_id"] == "oldest"

    @pytest.mark.asyncio
    async def test_update_title(self, repo):
        """Update conversation title."""
        await repo.create(conversation_id="conv-update", title="Original")

        await repo.update("conv-update", title="Updated")

        result = await repo.get("conv-update")
        assert result["title"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_status(self, repo):
        """Update conversation status."""
        await repo.create(conversation_id="conv-status", status="active")

        await repo.update("conv-status", status="archived")

        result = await repo.get("conv-status")
        assert result["status"] == "archived"

    @pytest.mark.asyncio
    async def test_update_summary(self, repo):
        """Update conversation summary."""
        await repo.create(conversation_id="conv-summary")

        await repo.update("conv-summary", summary="This is a summary")

        result = await repo.get("conv-summary")
        assert result["summary"] == "This is a summary"

    @pytest.mark.asyncio
    async def test_update_metadata(self, repo):
        """Update conversation metadata."""
        await repo.create(conversation_id="conv-meta", metadata={"old": True})

        await repo.update("conv-meta", metadata={"new": True})

        result = await repo.get("conv-meta")
        assert result["metadata"] == {"new": True}

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, repo):
        """Update multiple fields at once."""
        await repo.create(conversation_id="conv-multi", title="Old", status="active")

        await repo.update("conv-multi", title="New", status="archived")

        result = await repo.get("conv-multi")
        assert result["title"] == "New"
        assert result["status"] == "archived"

    @pytest.mark.asyncio
    async def test_delete_conversation(self, repo):
        """Delete removes conversation."""
        await repo.create(conversation_id="conv-delete")

        await repo.delete("conv-delete")

        result = await repo.get("conv-delete")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_cascades_to_runs(self, repo, db):
        """Delete cascades to associated runs."""
        await repo.create(conversation_id="conv-cascade")

        # Insert a run for this conversation (include all NOT NULL fields)
        await db.conn.execute(
            """
            INSERT INTO runs (run_id, conversation_id, created_at, status, profile_name, mode, model_config_snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("run-1", "conv-cascade", "2024-01-01T00:00:00Z", "succeeded", "chat", "chat", "{}"),
        )
        await db.conn.commit()

        await repo.delete("conv-cascade")

        # Run should also be deleted
        cursor = await db.conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", ("run-1",)
        )
        row = await cursor.fetchone()
        assert row is None
