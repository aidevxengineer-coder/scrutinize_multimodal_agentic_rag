from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.config import Settings
from app.core.deps import get_app_settings, get_db_session, get_v2_llm_client
from app.models.project import Project
from app.schemas.v1.agent import AgentChatRequest, AgentChatResponse
from app.services.agent_service import AgentService
from app.services.v2.llm_clients import BaseLlmClient

router = APIRouter(prefix="/projects", tags=["v1-agent"])


@router.post("/{project_id}/agent/chat", response_model=AgentChatResponse)
async def agent_chat(
    project_id: UUID,
    body: AgentChatRequest,
    session: Session = Depends(get_db_session),
    llm_client: BaseLlmClient = Depends(get_v2_llm_client),
    settings: Settings = Depends(get_app_settings),
) -> AgentChatResponse:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    agent_service = AgentService(session, llm_client, settings)
    return await agent_service.run_chat(project, body)
