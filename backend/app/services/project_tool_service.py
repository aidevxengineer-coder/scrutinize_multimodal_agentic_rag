import hmac
import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
import jsonschema
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.project_tool import ProjectTool
from app.schemas.v1.project_tool import ProjectToolCreate, ProjectToolUpdate

logger = logging.getLogger(__name__)


class ProjectToolService:
    """Service layer for project custom tool management and execution."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def validate_schema(schema: dict) -> None:
        """Verify that parameters_schema is a valid JSON schema."""
        if not isinstance(schema, dict):
            raise HTTPException(status_code=400, detail="parameters_schema must be a valid JSON object.")
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON Schema for tool parameters: {exc.message}")

    @staticmethod
    def validate_arguments(tool: ProjectTool, arguments: dict) -> None:
        """Validate LLM generated arguments against tool's parameter JSON Schema."""
        try:
            jsonschema.validate(instance=arguments, schema=tool.parameters_schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Argument validation failed for tool '{tool.name}': {exc.message}")

    def list_tools(self, project_id: UUID) -> list[ProjectTool]:
        statement = select(ProjectTool).where(ProjectTool.project_id == project_id).order_by(ProjectTool.name)
        return list(self.session.exec(statement).all())

    def get_active_tools(self, project_id: UUID) -> list[ProjectTool]:
        statement = (
            select(ProjectTool)
            .where(ProjectTool.project_id == project_id, ProjectTool.is_enabled == True)
            .order_by(ProjectTool.name)
        )
        return list(self.session.exec(statement).all())

    def get_tool(self, project_id: UUID, tool_id: UUID) -> ProjectTool:
        tool = self.session.get(ProjectTool, tool_id)
        if not tool or tool.project_id != project_id:
            raise HTTPException(status_code=4404 if False else 404, detail="Tool not found for this project.")
        return tool

    def get_tool_by_name(self, project_id: UUID, name: str) -> ProjectTool | None:
        statement = select(ProjectTool).where(ProjectTool.project_id == project_id, ProjectTool.name == name)
        return self.session.exec(statement).first()

    def create_tool(self, project_id: UUID, data: ProjectToolCreate) -> ProjectTool:
        # Check name uniqueness within project
        existing = self.get_tool_by_name(project_id, data.name)
        if existing:
            raise HTTPException(status_code=400, detail=f"A tool named '{data.name}' already exists in this project.")

        self.validate_schema(data.parameters_schema)

        tool = ProjectTool(
            project_id=project_id,
            name=data.name,
            display_name=data.display_name,
            description=data.description,
            is_enabled=data.is_enabled,
            execution_mode=data.execution_mode,
            webhook_url=data.webhook_url,
            webhook_method=data.webhook_method or "POST",
            webhook_headers=data.webhook_headers or {},
            parameters_schema=data.parameters_schema,
        )
        self.session.add(tool)
        self.session.commit()
        self.session.refresh(tool)
        return tool

    def update_tool(self, project_id: UUID, tool_id: UUID, data: ProjectToolUpdate) -> ProjectTool:
        tool = self.get_tool(project_id, tool_id)

        if data.name is not None and data.name != tool.name:
            existing = self.get_tool_by_name(project_id, data.name)
            if existing:
                raise HTTPException(status_code=400, detail=f"A tool named '{data.name}' already exists in this project.")
            tool.name = data.name

        if data.parameters_schema is not None:
            self.validate_schema(data.parameters_schema)
            tool.parameters_schema = data.parameters_schema

        if data.display_name is not None:
            tool.display_name = data.display_name
        if data.description is not None:
            tool.description = data.description
        if data.is_enabled is not None:
            tool.is_enabled = data.is_enabled
        if data.execution_mode is not None:
            tool.execution_mode = data.execution_mode
        if data.webhook_url is not None:
            tool.webhook_url = data.webhook_url
        if data.webhook_method is not None:
            tool.webhook_method = data.webhook_method
        if data.webhook_headers is not None:
            tool.webhook_headers = data.webhook_headers

        tool.updated_at = datetime.now(UTC)
        self.session.add(tool)
        self.session.commit()
        self.session.refresh(tool)
        return tool

    def toggle_tool(self, project_id: UUID, tool_id: UUID, is_enabled: bool) -> ProjectTool:
        tool = self.get_tool(project_id, tool_id)
        tool.is_enabled = is_enabled
        tool.updated_at = datetime.now(UTC)
        self.session.add(tool)
        self.session.commit()
        self.session.refresh(tool)
        return tool

    def delete_tool(self, project_id: UUID, tool_id: UUID) -> None:
        tool = self.get_tool(project_id, tool_id)
        self.session.delete(tool)
        self.session.commit()

    @staticmethod
    def to_openai_tool(tool: ProjectTool) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
            },
        }

    async def execute_webhook(
        self, tool: ProjectTool, arguments: dict, secret_key: str | None = None
    ) -> str:
        """Dispatch HTTP webhook call for server-executed tool mode."""
        if not tool.webhook_url:
            raise ValueError(f"Webhook URL is missing for tool '{tool.name}'.")

        payload = json.dumps(arguments)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Scrutinize-Agent-Webhook/1.0",
        }
        if tool.webhook_headers:
            headers.update(tool.webhook_headers)

        if secret_key:
            sig = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
            headers["X-Scrutinize-Signature"] = f"sha256={sig}"

        method = (tool.webhook_method or "POST").upper()

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                if method in ("GET", "HEAD"):
                    res = await client.request(method, tool.webhook_url, params=arguments, headers=headers)
                else:
                    res = await client.request(method, tool.webhook_url, content=payload, headers=headers)
                res.raise_for_status()
                return res.text
            except httpx.HTTPError as exc:
                logger.error(f"Webhook execution failed for tool '{tool.name}': {exc}")
                return json.dumps({"error": f"Webhook execution failed: {str(exc)}"})
