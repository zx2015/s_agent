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
