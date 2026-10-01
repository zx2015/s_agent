"""
Pydantic request/response shapes for the REST + SSE API.

Response models use `to_camel` aliasing so the JSON on the wire matches
`frontend/src/types/index.ts` field-for-field (`workspaceId`,
`hasArtifacts`, ...) — the frontend stores can consume them with zero
translation layer.
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

CamelModel = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TaskOut(BaseModel):
    model_config = CamelModel

    id: str
    title: str
    workspace_id: str
    status: Literal["running", "completed", "suspended", "failed"]
    updated_at: str
    has_artifacts: bool
    is_archived: bool = False
    workspace_path: str = ""


class WorkspaceOut(BaseModel):
    model_config = CamelModel

    id: str
    name: str
    tasks: list[TaskOut]


class CreateTaskRequest(BaseModel):
    model_config = CamelModel

    workspace_id: str = "default"
    title: str = "新任务"


class CreateWorkspaceRequest(BaseModel):
    model_config = CamelModel

    name: str


class UpdateTaskRequest(BaseModel):
    model_config = CamelModel

    title: str | None = None
    status: Literal["running", "completed", "suspended", "failed"] | None = None
    is_archived: bool | None = None


class ChatRequest(BaseModel):
    model_config = CamelModel

    task_id: str
    message: str
    model_name: str | None = None
    base_url: str | None = None
    hitl_mode: Literal["always", "dangerous", "never"] | None = None


class ConfirmRequest(BaseModel):
    model_config = CamelModel

    reply_id: str
    action: Literal["allow", "deny"]


def now_iso() -> str:
    """UTC timestamp in the format `updatedAt` fields use across the API."""
    return datetime.now(timezone.utc).isoformat()
