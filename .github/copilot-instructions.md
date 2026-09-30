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
- **The system prompt sent to the model is not just
  `SYSTEM_PROMPT_TEMPLATE`**: AgentScope assembles it in three layers at
  reply time (our fixed string + toolkit skill/offloader instructions +
  nothing else registered today), and separately injects a runtime-state
  `<system-reminder>` (current time, pending tasks) as its own context
  message rather than into the prompt string, so prompt caching on the
  fixed text still works. See CLAUDE.md's "System Prompt 的实际组装方式"
  section before changing prompt wording or debugging "the model doesn't
  know X". That runtime-state hint currently has no case in
  `AgentEventTranslator` and is silently dropped rather than surfaced to
  the frontend.
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

## MateChat component usage (frontend/src)

Beyond the `app.use(MateChat)` plugin install in `main.ts`, these
`@matechat/core` components are wired into real app structure/behavior
(not just installed-but-unused):

- **Layout**: `SidebarMiddle.vue` uses `McLayout`/`McLayoutHeader`/
  `McLayoutContent`/`McLayoutSender` for the header/messages/input stack;
  `McLayoutContent`'s built-in `ResizeObserver`-driven auto-scroll-to-bottom
  (with pause-on-scroll-up and jump arrows) replaced a hand-rolled
  `watch()` + `scrollTop = scrollHeight` in `MessageList.vue`.
  `SidebarLeft.vue`/`SidebarRight.vue` use `McLayoutAside` — its default
  CSS sets `flex-direction: row` (meant for icon rows), which both
  components override to `column !important` with a comment explaining
  why, since our sidebars are vertical stacks.
- **Chat surface**: `UserMessage.vue`/`AssistantMessage.vue` use
  `McBubble`; `ChatInput.vue` uses `McInput` (its `loading` prop drives
  the send-button↔cancel-button swap instead of a custom disabled state).
- **Markdown**: `AssistantMessage.vue` renders `message.text` with
  `McMarkdownCard` instead of a hand-rolled `markdown-it` +
  `highlight.js` pipeline (both removed from `package.json` — see
  `MarkdownCard/index.css` for the bundled `hljs-*` theme that made our
  own `highlight.js/styles/github.css` import redundant). `<think>` tag
  stripping still happens in `store/session.ts` (a real, already-tested
  quirk from a specific model provider in the `v-flash` rotation), not
  via `McMarkdownCard`'s `enableThink` — that prop only parses tags found
  inline in `content`, not the separate `thinking_delta` SSE channel,
  so the two rendering paths (event-based vs. inline-tag) would otherwise
  disagree on where "thinking" content shows up.
- **Actions**: `AssistantMessage.vue` shows an `McToolbar` with only a
  `copy` action (`ToolbarAction.COPY`, from `@matechat/core/Toolbar`) once
  a reply finishes — `McCopyIcon` handles the clipboard write itself via
  the `text` field on the action item; no other toolbar action (like/
  dislike/refresh/share) is wired up because none has real backend
  behavior yet, and a decorative button that does nothing is worse than
  no button.
- **Task list**: `WorkspaceTree.vue` renders each workspace's tasks with
  `McList` (`variant="none"` was considered and rejected — it skips
  McList's own click/active-state wiring entirely, which would make using
  the component pointless; `variant="transparent"` is used instead, with
  the existing status-dot/title/artifact-badge markup living inside the
  `#item` slot). The collapsible per-workspace *grouping* has no MateChat
  equivalent, so that part is still custom.
- **Top bar**: `App.vue` uses `McHeader` with the active task name in its
  `#operationArea` slot.
- **Onboarding**: `MessageList.vue`'s empty state uses `McIntroduction`
  with `McPrompt` suggestion chips; clicking one calls `useChat().send()`
  directly (runs the example immediately, rather than just filling the
  input) — see the chips' list in that file for what the agent can
  actually do today.
- **jsdom gap**: `McLayoutContent` constructs a real `ResizeObserver` in
  `setup()` unconditionally. jsdom doesn't implement one, so
  `frontend/tests/setup.ts` (wired via `vite.config.ts`'s
  `test.setupFiles`) stubs a no-op `ResizeObserver` globally — any test
  that mounts something nesting `McLayoutContent` needs this to not throw
  before a single assertion runs.

Not adopted, deliberately: `McAttachment`/`McFileList`/`McMention` (no
attachment-upload backend exists yet — spec explicitly defers this) and
`McRefreshIcon`/`McLikeIcon`/`McDislikeIcon` (would need real regenerate/
feedback endpoints to not be decorative).

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
