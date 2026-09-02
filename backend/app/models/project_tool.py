from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, String
from sqlmodel import Field, SQLModel


class ProjectTool(SQLModel, table=True):
    """Represents a project-scoped custom tool definition for agentic execution."""

    __tablename__ = "project_tools"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    
    name: str = Field(sa_column=Column(String(64), nullable=False))
    display_name: str = Field(sa_column=Column(String(128), nullable=False))
    description: str = Field(nullable=False)
    is_enabled: bool = Field(default=True, nullable=False)

    # Execution Mode: 'client_delegated' (caller executes) or 'server_webhook' (Scrutinize executes HTTP webhook)
    execution_mode: str = Field(default="client_delegated", sa_column=Column(String(32), nullable=False))

    # For 'server_webhook' mode
    webhook_url: str | None = Field(default=None, nullable=True)
    webhook_method: str | None = Field(default="POST", sa_column=Column(String(10), nullable=True))
    webhook_headers: dict | None = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))

    # JSON Schema defining expected inputs/arguments for the LLM
    parameters_schema: dict = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []},
        sa_column=Column(JSON, nullable=False),
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
