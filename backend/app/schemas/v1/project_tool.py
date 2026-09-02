import re
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


TOOL_NAME_REGEX = r"^[a-zA-Z0-9_-]{1,64}$"


class ProjectToolCreate(BaseModel):
    name: str = Field(..., description="Tool machine name, alphanumeric with dashes/underscores, max 64 chars")
    display_name: str = Field(..., max_length=128, description="Human-readable title")
    description: str = Field(..., description="Detailed description of tool purpose for LLM reasoning")
    is_enabled: bool = Field(default=True)
    execution_mode: Literal["client_delegated", "server_webhook"] = Field(default="client_delegated")
    webhook_url: str | None = Field(default=None)
    webhook_method: str | None = Field(default="POST")
    webhook_headers: dict | None = Field(default_factory=dict)
    parameters_schema: dict = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not re.match(TOOL_NAME_REGEX, trimmed):
            raise ValueError(
                "Tool name must be 1-64 characters long and contain only letters, numbers, underscores, or hyphens."
            )
        return trimmed


class ProjectToolUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    is_enabled: bool | None = None
    execution_mode: Literal["client_delegated", "server_webhook"] | None = None
    webhook_url: str | None = None
    webhook_method: str | None = None
    webhook_headers: dict | None = None
    parameters_schema: dict | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        trimmed = v.strip()
        if not re.match(TOOL_NAME_REGEX, trimmed):
            raise ValueError(
                "Tool name must be 1-64 characters long and contain only letters, numbers, underscores, or hyphens."
            )
        return trimmed


class ProjectToolToggle(BaseModel):
    is_enabled: bool


class ProjectToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    display_name: str
    description: str
    is_enabled: bool
    execution_mode: str
    webhook_url: str | None = None
    webhook_method: str | None = None
    webhook_headers: dict | None = None
    parameters_schema: dict
    created_at: datetime
    updated_at: datetime
