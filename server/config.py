"""
Runtime configuration, read entirely from the environment.

CLAUDE.md pins the model wiring (LiteLLM `v-flash`, base_url only on the
credential) and forbids hardcoding secrets — this module is the single
place those environment variables are read, so nothing downstream needs
`os.getenv` of its own.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

# --- Model wiring (see CLAUDE.md "模型接入" section) ---
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
MODEL_NAME = os.getenv("S_AGENT_MODEL_NAME", "v-flash")
MODEL_MAX_TOKENS = int(os.getenv("S_AGENT_MODEL_MAX_TOKENS", "2048"))

# A separate, deliberately small/cheap model for one-shot, low-stakes text
# generation (currently: auto-titling a new conversation from its first
# message — see server/service/title_generator.py). Using the same model
# as the main agent (`MODEL_NAME`) would work but wastes its larger
# per-token cost and latency on a task that a "flash-lite" tier model
# handles just as well.
MODEL_NAME_TITLE = os.getenv("S_AGENT_TITLE_MODEL_NAME", "Gemini/Gemini-3.5-Flash-Lite")

# --- Workspace storage ---
# Gitignored (see .gitignore's `workspaces/` entry) so per-task file trees
# and the task/workspace registry never enter version control.
WORKSPACES_ROOT = Path(
    os.getenv("S_AGENT_WORKSPACES_ROOT", str(REPO_ROOT / "workspaces")),
)

# --- CORS ---
# Only needed when the frontend talks to :8000 directly instead of through
# the Vite dev proxy (vite.config.ts `server.proxy['/api']`).
ALLOWED_ORIGINS = os.getenv(
    "S_AGENT_ALLOWED_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173",
).split(",")

# --- Conversation history persistence ---
# Backed by the local Redis container (see CLAUDE.md's environment notes;
# host port 6380, no password). Each task's AgentState is stored as one
# key so a backend restart doesn't wipe conversation history the way an
# in-memory-only TaskManager._agents cache does — see
# server/service/memory_store.py.
REDIS_URL = os.getenv("S_AGENT_REDIS_URL", "redis://127.0.0.1:6380/0")
# How long a task's saved conversation survives with no activity before
# Redis evicts it. Refreshed on every save, so only genuinely abandoned
# tasks expire.
AGENT_STATE_TTL_SECONDS = int(
    os.getenv("S_AGENT_STATE_TTL_DAYS", "30"),
) * 86400

# --- MCP (Model Context Protocol) servers ---
# JSON array of {"name", "url", "is_stateful"?} objects fed to AgentScope
# as external tools. Default is the local Tavily container
# (docker container `mcp-tavily`, host port 18000, Streamable HTTP at
# /mcp) — verified reachable on 2026-09-30 via a curl initialize probe.
# Set to "" (or comment out) to disable MCP entirely.
MCP_SERVERS = os.getenv(
    "S_AGENT_MCP_SERVERS",
    '[{"name": "tavily", "url": "http://127.0.0.1:18000/mcp"}]',
)
