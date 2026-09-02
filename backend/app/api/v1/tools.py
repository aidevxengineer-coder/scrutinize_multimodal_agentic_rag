from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.deps import get_db_session
from app.schemas.v1.project_tool import (
    ProjectToolCreate,
    ProjectToolRead,
    ProjectToolToggle,
    ProjectToolUpdate,
)
from app.services.project_tool_service import ProjectToolService

router = APIRouter(prefix="/projects", tags=["v1-tools"])


@router.get("/{project_id}/tools", response_model=list[ProjectToolRead])
def list_project_tools(
    project_id: UUID,
    session: Session = Depends(get_db_session),
) -> list[ProjectToolRead]:
    service = ProjectToolService(session)
    return [ProjectToolRead.model_validate(t) for t in service.list_tools(project_id)]


@router.post("/{project_id}/tools", response_model=ProjectToolRead, status_code=201)
def create_project_tool(
    project_id: UUID,
    body: ProjectToolCreate,
    session: Session = Depends(get_db_session),
) -> ProjectToolRead:
    service = ProjectToolService(session)
    tool = service.create_tool(project_id, body)
    return ProjectToolRead.model_validate(tool)


@router.get("/{project_id}/tools/{tool_id}", response_model=ProjectToolRead)
def get_project_tool(
    project_id: UUID,
    tool_id: UUID,
    session: Session = Depends(get_db_session),
) -> ProjectToolRead:
    service = ProjectToolService(session)
    tool = service.get_tool(project_id, tool_id)
    return ProjectToolRead.model_validate(tool)


@router.put("/{project_id}/tools/{tool_id}", response_model=ProjectToolRead)
def update_project_tool(
    project_id: UUID,
    tool_id: UUID,
    body: ProjectToolUpdate,
    session: Session = Depends(get_db_session),
) -> ProjectToolRead:
    service = ProjectToolService(session)
    tool = service.update_tool(project_id, tool_id, body)
    return ProjectToolRead.model_validate(tool)


@router.patch("/{project_id}/tools/{tool_id}/toggle", response_model=ProjectToolRead)
def toggle_project_tool(
    project_id: UUID,
    tool_id: UUID,
    body: ProjectToolToggle,
    session: Session = Depends(get_db_session),
) -> ProjectToolRead:
    service = ProjectToolService(session)
    tool = service.toggle_tool(project_id, tool_id, body.is_enabled)
    return ProjectToolRead.model_validate(tool)


@router.delete("/{project_id}/tools/{tool_id}", status_code=204)
def delete_project_tool(
    project_id: UUID,
    tool_id: UUID,
    session: Session = Depends(get_db_session),
) -> None:
    service = ProjectToolService(session)
    service.delete_tool(project_id, tool_id)
