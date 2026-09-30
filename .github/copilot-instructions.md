# Copilot Instructions for s_agent

## Project state

Both halves of the stack exist and are wired together:

- `frontend/` — Vue 3 + TypeScript + Vite workbench UI, using MateChat
  (`@matechat/core`) components for chat surfaces.
- `server/` — FastAPI + AgentScope 2.0.8 backend exposing the SSE chat
  contract and REST task/workspace endpoints.

Full project conventions (venv path, AgentScope 2.0.8 API quirks, LiteLLM
`v-flash` model wiring, stock-analysis-phase rules) live in `CLAUDE.md` at
the repo root — read it before touching model/tool wiring. `TODO.md`
tracks what's still open (memory persistence across restarts, HITL rule
refinement, stock-analysis tools) — check it before assuming a feature is
missing.

## Build, test, lint

### Frontend (run from `frontend/`)

```bash
npm install          # first time / after dependency changes
npm run dev          # Vite dev server on :5173, proxies /api -> :8000
npm run build        # vue-tsc -b (typecheck) && vite build
npm run test         # vitest run (all specs)
npm run test:watch   # vitest watch mode
```

Run a single test file or case with vitest directly:

```bash
npx vitest run tests/store/session.spec.ts
npx vitest run tests/store/session.spec.ts -t "unwraps think tags"
```

Test files live under `frontend/tests/**/*.spec.ts` (mirroring `src/`
structure: `api/`, `mock/`, `store/`, `components/`, `composables/`), not
colocated with source — vitest is configured via `include:
['tests/**/*.spec.ts']` in `vite.config.ts`.

### Backend (run from the repo root, using the pinned venv)

```bash
VENV_PYTHON=/media/data/venv/bin/python

# Start the dev server (reload on save)
$VENV_PYTHON -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

# Run all backend tests
$VENV_PYTHON -m pytest tests/ -v

# Run a single test file or case
$VENV_PYTHON -m pytest tests/test_events.py -v
$VENV_PYTHON -m pytest tests/test_events.py::test_reply_end_frame_reports_completed_and_failed -v

# Health check / manual SSE probe
curl -s http://127.0.0.1:8000/api/health
curl -sN -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" \
  -d '{"taskId": "<id from /api/workspaces>", "message": "你好"}'
```

Backend config is read entirely from the environment via `server/config.py`
(loads `.env` at repo root through `python-dotenv`). Copy `.env.example` to
`.env` and set `LITELLM_API_KEY` before starting the server — without it,
`/api/chat` degrades gracefully (an SSE error frame + `done`), it does not
throw a 500.

## Architecture: three-column workbench + SSE contract

The frontend is a chat "workbench" UI (left task tree / middle chat stream /
right artifacts panel), fully specified in
`docs/specs/2026-09-28-frontend-three-column-workbench.md`. The backend
implements that spec's §3 SSE/REST contract exactly. Key structural points
that span multiple files:

- **The SSE wire contract is defined twice, deliberately, and the two must
  change together:**
  - `frontend/src/api/events.ts` — the 7 event names (`thinking_delta`,
    `text_delta`, `tool_call_start`, `tool_call_end`, `artifact_created`,
    `require_confirm`, `done`) and their payload shapes, plus
    `parseSseFrame`/`splitSseBuffer` for chunk-boundary-safe parsing.
  - `server/service/events.py` — `AgentEventTranslator` converts
    AgentScope's own event stream (`ThinkingBlockDeltaEvent`,
    `ToolCallStartEvent`/`ToolCallDeltaEvent`, `ToolResultEndEvent`,
    `RequireUserConfirmEvent`, `ReplyEndEvent`, ...) into frames matching
    that contract field-for-field. AgentScope splits a tool call's
    arguments and its result text into separate delta events from the
    "start"/"end" events — the translator buffers both per
    `tool_call_id` and flushes them into single `tool_call_start`/
    `tool_call_end` frames.
- **`frontend/src/store/session.ts` (Pinia)** is where SSE frames become UI
  state via `applyFrame()`. Two non-obvious behaviors live here rather than
  in components: `<think>` tag unwrapping across chunk boundaries (a
  module-level `insideThink` state machine), and turn-guarding (frames are
  dropped unless `turnOpen` is true, so a straggler after a reset can't
  repopulate a cleared conversation).
- **`frontend/src/mock/sse-server.ts`** simulates the backend stream so the
  frontend is buildable without it running. Toggle with `VITE_USE_MOCK=true`
  (see `src/composables/useChat.ts`); the real path goes through the Vite
  dev proxy (`vite.config.ts` `server.proxy['/api']` → `:8000`).
- **HITL confirm loop**: AgentScope's `reply_stream()` yields
  `RequireUserConfirmEvent` and then ends; resuming means calling
  `reply_stream()` again with a `UserConfirmResultEvent`. Because the SSE
  response is one long-lived generator and the confirm action arrives on a
  *separate* HTTP request, `server/service/task_manager.py` bridges them
  with an `asyncio.Future` keyed by `reply_id`: the chat generator awaits
  it, `POST /api/tasks/{id}/confirm` resolves it. The frontend's
  `useChat().confirmToolCall()` calls that endpoint; `HitlConfirmCard.vue`
  never resolves the pending confirm locally without also notifying the
  backend.
- **Per-task isolation**: `TaskManager.get_or_create_agent()` builds one
  AgentScope `Agent` (with its own `Toolkit`, workspace directory, and git
  repo) per task id, lazily on first message. Two tasks never share
  conversation history or file access. `server/agent/core.py` assembles the
  toolkit — AgentScope 2.0.8 ships `Bash`/`Read`/`Write`/`Edit`/`Glob`/
  `Grep`/`AskUser`/`TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate` as
  built-ins; only `server/tools/calculator.py` (a restricted-AST arithmetic
  evaluator, per `CLAUDE.md`'s "严禁心算" rule) is project-specific.
- **Artifact detection is mtime-based, not tool-hook-based**: after each
  turn's `ReplyEndEvent`, `server/main.py`'s `_new_artifact_frames()` scans
  the task's workspace directory for files modified since the turn started
  and emits `artifact_created` for each — this way any tool that touches
  the filesystem (`Write`, `Edit`, or a `Bash` command) surfaces its output
  the same way, without per-tool special-casing.
- **`frontend/src/types/index.ts`** holds UI-facing domain types
  (camelCase) distinct from the snake_case wire types in `api/events.ts`;
  `server/schemas/chat.py` uses Pydantic's `to_camel` alias generator so
  REST JSON matches those UI types field-for-field with no translation
  layer needed on the frontend.

## Key conventions

- Two-space indent, no semicolons in frontend `.ts`/`.vue` files; match
  surrounding style rather than reformatting whole files.
- Path alias `@/*` → `frontend/src/*` (configured in both `vite.config.ts`
  and `tsconfig`).
- `vite.config.ts` auto-generates a `resolve.alias` entry for every
  `@matechat/core/<Subpackage>` directory (see the `matechatSubpathAliases`
  block) — `@matechat/core` ships only a `module` field with no `exports`
  map, and its subpackages import each other as bare directory specifiers,
  which Vite's browser bundling tolerates but vitest's stricter Node ESM
  resolver does not. If you add new MateChat usage and hit a "Failed to
  resolve import" error in tests only, this is almost always why — check
  the alias generation still covers the subpackage before adding anything
  by hand.
- Doc comments (`/** ... */` / Python docstrings) are used liberally at
  file-top and above non-obvious functions to explain *why*, not *what* —
  follow that pattern for tricky logic (state machines, protocol glue,
  AgentScope API quirks), skip it for straightforward code.
- `TODO.md` is version-controlled and must be kept current: move finished
  items to "已完成" with a date instead of deleting them; don't delete
  in-progress/pending items either. `.learnings/`, `.claude/`, and
  `workspaces/` (per-task working directories + the task/workspace JSON
  registry) are git-ignored local-only state — never add files there to a
  commit. `.env` is git-ignored too; only `.env.example` is tracked.
- Secrets (`LITELLM_API_KEY`) are read only in `server/config.py` — no
  other module should call `os.getenv` directly for them.
