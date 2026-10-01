"""Unit tests for Context Offload and workspace persistence wiring."""
import asyncio
import base64
import json
from pathlib import Path

import pytest
from agentscope.agent import ContextConfig
from agentscope.message import Msg, TextBlock, ToolResultBlock, DataBlock, Base64Source
from agentscope.tool import LocalBackend, Read
from agentscope.workspace import LocalWorkspace

from server import config
from server.agent.core import build_agent


@pytest.mark.asyncio
async def test_build_agent_configures_offloader_and_context_config(tmp_path: Path):
    """build_agent must mount LocalWorkspace as offloader and calibrate context_size."""
    agent = await build_agent(tmp_path)

    assert isinstance(agent.offloader, LocalWorkspace)
    assert agent.offloader.workdir == str(tmp_path.resolve())
    assert agent.context_config.tool_result_limit == config.TOOL_RESULT_LIMIT
    assert agent.context_config.trigger_ratio == config.CONTEXT_TRIGGER_RATIO
    assert agent.context_config.reserve_ratio == config.CONTEXT_RESERVE_RATIO
    assert agent.model.context_size > 0
    if config.MODEL_CONTEXT_SIZE > 0:
        assert agent.model.context_size == config.MODEL_CONTEXT_SIZE


@pytest.mark.asyncio
async def test_tool_result_offloading_and_truncation(tmp_path: Path):
    """Large tool results exceeding tool_result_limit must be split and saved to disk."""
    ws = LocalWorkspace(workdir=str(tmp_path))
    agent = await build_agent(tmp_path)

    # Override tool_result_limit to a small threshold for testing
    agent.context_config.tool_result_limit = 10

    raw_output = "Line 1: important header info\n" + "Line X: long data chunk " * 20
    tool_result = ToolResultBlock(
        id="call_mock_12345",
        name="test_runner",
        output=raw_output,
    )

    reserved, offloaded = await agent._split_tool_result_for_compression(tool_result)

    assert offloaded is not None
    assert reserved is not None
    assert len(reserved.output) > 0
    assert len(offloaded.output) > 0

    # Offload to disk via the workspace offloader
    offload_path = await agent.offloader.offload_tool_result(
        agent.state.session_id,
        offloaded,
    )

    saved_file = Path(offload_path)
    assert saved_file.exists()
    assert saved_file.is_file()
    assert "sessions" in str(saved_file)
    assert f"tool_result-{tool_result.id}.txt" in saved_file.name

    content = saved_file.read_text(encoding="utf-8")
    assert "long data chunk" in content


@pytest.mark.asyncio
async def test_read_tool_reads_offloaded_file(tmp_path: Path):
    """The built-in Read tool must be able to read back the offloaded file."""
    ws = LocalWorkspace(workdir=str(tmp_path))
    session_id = "test_sess_001"
    tool_result = ToolResultBlock(
        id="call_read_back",
        name="log_collector",
        output="[CRITICAL ERROR] database connection timed out on worker 4",
    )

    saved_path = await ws.offload_tool_result(session_id, tool_result)
    assert Path(saved_path).exists()

    backend = LocalBackend()
    read_tool = Read(backend=backend)
    result = await read_tool(file_path=saved_path)

    # Read output contains numbered text blocks
    text_content = "".join(b.text for b in result.content if isinstance(b, TextBlock))
    assert "[CRITICAL ERROR] database connection timed out" in text_content


@pytest.mark.asyncio
async def test_context_compression_offloads_history_jsonl(tmp_path: Path):
    """Offloader.offload_context must append uncompressed messages to context.jsonl."""
    ws = LocalWorkspace(workdir=str(tmp_path))
    session_id = "sess_archive_test"

    msgs = [
        Msg(name="user", role="user", content=[TextBlock(text="Analyze stock 600519")]),
        Msg(name="assistant", role="assistant", content=[TextBlock(text="Analyzing financial metrics for 600519...")]),
    ]

    path = await ws.offload_context(session_id, msgs)
    saved_file = Path(path)

    assert saved_file.exists()
    assert saved_file.name == "context.jsonl"

    lines = saved_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    parsed_0 = json.loads(lines[0])
    assert parsed_0["name"] == "user"
    assert parsed_0["content"][0]["text"] == "Analyze stock 600519"


@pytest.mark.asyncio
async def test_data_block_offload(tmp_path: Path):
    """Base64 DataBlock must be decoded and persisted to data/ directory."""
    ws = LocalWorkspace(workdir=str(tmp_path))
    dummy_bytes = b"PNG_FAKE_IMAGE_DATA_123456"
    b64_data = base64.b64encode(dummy_bytes).decode("ascii")

    block = DataBlock(
        name="stock_chart.png",
        source=Base64Source(
            data=b64_data,
            media_type="image/png",
        ),
    )

    offloaded_block = await ws.offload_data_block(block)

    # Must return workspace:// URL
    url = str(offloaded_block.source.url)
    assert url.startswith("workspace:///data/")

    # Physical file exists under workdir/data/
    data_dir = tmp_path / "data"
    assert data_dir.exists()
    files = list(data_dir.glob("*.png"))
    assert len(files) == 1
    assert files[0].read_bytes() == dummy_bytes
