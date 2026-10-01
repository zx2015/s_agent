"""Unit tests for server/service/task_manager.py's persistence wiring."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from server.service.memory_store import agent_state_store
from server.service.task_manager import TaskManager


@pytest.fixture
def manager(tmp_path: Path) -> TaskManager:
    """An isolated TaskManager instance rooted at a temporary directory.

    Passing an explicit root_dir guarantees these tests never write to the
    developer's real `workspaces/registry.json` or pollute the sidebar with
    fixture names like "我的新工作区".
    """
    return TaskManager(root_dir=tmp_path)


@pytest.mark.asyncio
async def test_save_agent_state_is_a_noop_when_agent_was_never_built(manager: TaskManager):
    # No get_or_create_agent() call happened for this id, so there is
    # nothing in manager._agents — must not raise.
    await manager.save_agent_state("never-touched-task")


@pytest.mark.asyncio
async def test_save_agent_state_swallows_persistence_failures(manager: TaskManager):
    """A Redis hiccup during save must not raise past this call.

    By the time save_agent_state() runs, the turn's SSE frames (including
    the translator's `done` frame for ReplyEndEvent) have already reached
    the client — see server/main.py's chat handler. If this raised, the
    caller's outer except would send a second, spurious done/error frame
    after an otherwise-successful reply.
    """
    fake_agent = type("FakeAgent", (), {"state": object()})()
    manager._agents["t1"] = fake_agent  # type: ignore[assignment]

    with patch(
        "server.service.task_manager.agent_state_store.save",
        new=AsyncMock(side_effect=ConnectionError("redis unreachable")),
    ):
        # Must not raise.
        await manager.save_agent_state("t1")


@pytest.mark.asyncio
async def test_delete_task_returns_false_for_an_unknown_task(manager: TaskManager):
    assert await manager.delete_task("does-not-exist") is False


@pytest.mark.asyncio
async def test_delete_task_removes_metadata_agent_state_and_workspace(manager: TaskManager):
    task = manager.create_task("default", "待删除的测试任务")
    workspace_dir = manager.workspace_dir(task.id)
    assert workspace_dir.exists()

    # Populate an in-memory agent placeholder and a Redis-persisted state
    # so the test proves both actually get cleaned up, not just metadata.
    manager._agents[task.id] = object()  # type: ignore[assignment]
    from agentscope.state import AgentState

    await agent_state_store.save(task.id, AgentState())

    deleted = await manager.delete_task(task.id)

    assert deleted is True
    assert manager.get_task(task.id) is None
    assert task.id not in manager._agents
    assert not workspace_dir.exists()
    assert await agent_state_store.load(task.id) is None


@pytest.mark.asyncio
async def test_delete_task_swallows_redis_failures(manager: TaskManager):
    """A Redis hiccup during delete must not stop metadata/file cleanup."""
    task = manager.create_task("default", "redis失败时也要删除的任务")

    with patch(
        "server.service.task_manager.agent_state_store.delete",
        new=AsyncMock(side_effect=ConnectionError("redis unreachable")),
    ):
        deleted = await manager.delete_task(task.id)

    assert deleted is True
    assert manager.get_task(task.id) is None
    assert not manager.workspace_dir(task.id).exists()


def test_create_workspace_assigns_a_fresh_id_and_the_given_display_name(manager: TaskManager):
    workspace = manager.create_workspace("我的新工作区")

    assert workspace.name == "我的新工作区"
    assert workspace.id != "我的新工作区"  # unlike create_task's implicit path

    listed = {w["id"]: w["name"] for w in manager.list_workspaces()}
    assert listed[workspace.id] == "我的新工作区"


def test_create_workspace_starts_with_no_tasks(manager: TaskManager):
    workspace = manager.create_workspace("空的工作区")

    listed = {w["id"]: w for w in manager.list_workspaces()}
    assert listed[workspace.id]["tasks"] == []


def test_created_workspace_can_receive_tasks(manager: TaskManager):
    workspace = manager.create_workspace("可以建任务的工作区")
    task = manager.create_task(workspace.id, "这个工作区里的第一个任务")

    listed = {w["id"]: w for w in manager.list_workspaces()}
    assert [t["id"] for t in listed[workspace.id]["tasks"]] == [task.id]


@pytest.mark.asyncio
async def test_delete_workspace_returns_false_for_an_unknown_workspace(manager: TaskManager):
    assert await manager.delete_workspace("does-not-exist") is False


@pytest.mark.asyncio
async def test_delete_workspace_cascades_to_every_task_inside_it(manager: TaskManager):
    workspace = manager.create_workspace("待整体删除的工作区")
    task_a = manager.create_task(workspace.id, "任务A")
    task_b = manager.create_task(workspace.id, "任务B")
    workspace_dir_a = manager.workspace_dir(task_a.id)
    workspace_dir_b = manager.workspace_dir(task_b.id)
    assert workspace_dir_a.exists()
    assert workspace_dir_b.exists()

    deleted = await manager.delete_workspace(workspace.id)

    assert deleted is True
    assert manager.get_task(task_a.id) is None
    assert manager.get_task(task_b.id) is None
    assert not workspace_dir_a.exists()
    assert not workspace_dir_b.exists()
    workspace_ids = {w["id"] for w in manager.list_workspaces()}
    assert workspace.id not in workspace_ids


@pytest.mark.asyncio
async def test_delete_workspace_leaves_other_workspaces_untouched(manager: TaskManager):
    workspace_to_delete = manager.create_workspace("要删的工作区")
    workspace_to_keep = manager.create_workspace("要留的工作区")
    manager.create_task(workspace_to_delete.id, "会被删掉的任务")
    kept_task = manager.create_task(workspace_to_keep.id, "应该留下的任务")

    await manager.delete_workspace(workspace_to_delete.id)

    assert manager.get_task(kept_task.id) is not None
    workspace_ids = {w["id"] for w in manager.list_workspaces()}
    assert workspace_to_keep.id in workspace_ids


@pytest.mark.asyncio
async def test_delete_workspace_with_no_tasks_just_removes_the_workspace(manager: TaskManager):
    workspace = manager.create_workspace("空的待删工作区")

    deleted = await manager.delete_workspace(workspace.id)

    assert deleted is True
    workspace_ids = {w["id"] for w in manager.list_workspaces()}
    assert workspace.id not in workspace_ids


@pytest.mark.asyncio
async def test_delete_workspace_refuses_to_delete_the_default_workspace(manager: TaskManager):
    task = manager.create_task("default", "不该被牵连的任务")

    deleted = await manager.delete_workspace("default")

    assert deleted is False
    workspace_ids = {w["id"] for w in manager.list_workspaces()}
    assert "default" in workspace_ids
    assert manager.get_task(task.id) is not None


def test_create_task_does_not_initialize_git(manager: TaskManager):
    """Creating a task must only create a directory without running git init."""
    task = manager.create_task("default", "无需git的任务")
    task_dir = manager.workspace_dir(task.id)

    assert task_dir.exists()
    assert not (task_dir / ".git").exists()


def test_archive_task_persists_across_reloads(tmp_path: Path):
    """Archiving a task sets is_archived=True and persists to disk."""
    m1 = TaskManager(root_dir=tmp_path)
    task = m1.create_task("default", "待归档任务")
    assert task.is_archived is False

    updated = m1.archive_task(task.id)
    assert updated is not None
    assert updated.is_archived is True

    # Reload from disk
    m2 = TaskManager(root_dir=tmp_path)
    loaded = m2.get_task(task.id)
    assert loaded is not None
    assert loaded.is_archived is True


@pytest.mark.asyncio
async def test_reset_context_clears_agent_and_redis(manager: TaskManager):
    """reset_context removes agent from cache and deletes state from Redis."""
    task = manager.create_task("default", "重置记忆任务")
    fake_agent = type("FakeAgent", (), {"state": "some-state"})()
    manager._agents[task.id] = fake_agent  # type: ignore[assignment]
    manager._agent_configs[task.id] = {"model_name": "test-model"}

    with patch.object(agent_state_store, "delete", new=AsyncMock()) as mock_delete:
        await manager.reset_context(task.id)
        assert task.id not in manager._agents
        assert task.id not in manager._agent_configs
        mock_delete.assert_awaited_once_with(task.id)


@pytest.mark.asyncio
async def test_get_or_create_agent_hot_reload_on_config_change(manager: TaskManager):
    """get_or_create_agent rebuilds the agent if model_name or hitl_mode changed."""
    task = manager.create_task("default", "配置热切换任务")
    
    mock_agent_1 = type("MockAgent1", (), {"state": "state1"})()
    mock_agent_2 = type("MockAgent2", (), {"state": "state2"})()

    with patch("server.service.task_manager.build_agent", new=AsyncMock(side_effect=[mock_agent_1, mock_agent_2])) as mock_build:
        # First call creates initial agent
        a1 = await manager.get_or_create_agent(task.id, model_name="model-a", hitl_mode="dangerous")
        assert a1 is mock_agent_1
        assert mock_build.call_count == 1

        # Second call with same parameters returns cached instance
        a1_cached = await manager.get_or_create_agent(task.id, model_name="model-a", hitl_mode="dangerous")
        assert a1_cached is mock_agent_1
        assert mock_build.call_count == 1

        # Third call with changed model triggers rebuild with previous state
        a2 = await manager.get_or_create_agent(task.id, model_name="model-b", hitl_mode="always")
        assert a2 is mock_agent_2
        assert mock_build.call_count == 2
        # Check that state was passed from a1
        _, kwargs = mock_build.call_args
        assert kwargs["model_name"] == "model-b"
        assert kwargs["hitl_mode"] == "always"
        assert kwargs["state"] == "state1"

