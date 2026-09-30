"""Unit tests for server/agent/core.py's system prompt assembly."""
from pathlib import Path

from server.agent.core import (
    SYSTEM_PROMPT_TEMPLATE,
    _build_environment_block,
    _detect_platform,
    _detect_shell,
)


def test_detect_platform_returns_linux_on_this_host():
    # The test suite only ever runs on Linux CI/dev boxes today; this pins
    # down the mapping (Darwin -> macos, Linux -> linux) rather than the
    # specific host.
    assert _detect_platform() == "linux"


def test_detect_shell_resolves_the_real_sh_target():
    # /bin/sh is what agentscope's Bash tool actually execs (see the
    # docstring on _detect_shell) — on many distros it's a symlink to
    # `dash`, not `bash`, so this must not just return a hardcoded guess.
    shell = _detect_shell()
    assert shell and "/" not in shell


def test_environment_block_reports_git_repo_presence(tmp_path):
    (tmp_path / ".git").mkdir()
    block = _build_environment_block(tmp_path)
    assert "<env>" in block and "</env>" in block
    assert "Is directory a git repo: Yes" in block
    assert str(tmp_path) in block


def test_environment_block_reports_non_git_directory(tmp_path):
    block = _build_environment_block(tmp_path)
    assert "Is directory a git repo: No" in block


def test_environment_block_includes_configured_model_name(tmp_path):
    block = _build_environment_block(tmp_path)
    from server import config

    assert f"Model: {config.MODEL_NAME}" in block


def test_system_prompt_template_has_required_placeholders():
    # A regression guard: the template must keep both format placeholders
    # so build_agent()'s .format(...) call doesn't silently drop the
    # environment block or the workspace path.
    rendered = SYSTEM_PROMPT_TEMPLATE.format(
        workspace_dir="/tmp/x",
        environment_block="<env>test</env>",
    )
    assert "/tmp/x" in rendered
    assert "<env>test</env>" in rendered


def test_system_prompt_covers_the_four_required_behaviors():
    rendered = SYSTEM_PROMPT_TEMPLATE.format(
        workspace_dir="/tmp/x",
        environment_block="<env/>",
    )
    assert "Markdown" in rendered  # GFM rendering note
    assert "拒绝" in rendered  # permission-mode / rejected tool call note
    assert "<system-reminder>" in rendered  # system-reminder origin note
    assert "中间件" in rendered  # hooks/middleware note
