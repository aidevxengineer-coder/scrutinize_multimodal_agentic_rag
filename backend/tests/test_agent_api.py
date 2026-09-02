import pytest
from sqlmodel import Session, create_engine, SQLModel

from app.models.project import Project
from app.schemas.v1.agent import AgentChatRequest
from app.schemas.v1.project_tool import ProjectToolCreate
from app.services.agent_service import AgentService
from app.services.project_tool_service import ProjectToolService
from app.services.v2.llm_clients.base import BaseLlmClient, LlmResponse, ToolCall


class FakeLlmClient(BaseLlmClient):
    def __init__(self, response_text: str = "Default answer", tool_calls: list[ToolCall] | None = None):
        self.response_text = response_text
        self.tool_calls = tool_calls

    def generate(self, model, system, user, *, json_mode=False, tools=None):
        return LlmResponse(
            content=self.response_text,
            model_name=model,
            prompt_system=system,
            prompt_user=user,
            tool_calls=self.tool_calls,
        )

    def generate_stream(self, model, system, user):
        yield self.response_text


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.mark.asyncio
async def test_agent_chat_returns_stop_when_no_tool_needed(db_session: Session):
    project = Project(name="Agent Proj 1", api_key="sk_ag_1", client_key="pk_ag_1")
    db_session.add(project)
    db_session.commit()

    llm = FakeLlmClient(response_text="Hello! How can I help you today?")
    service = AgentService(db_session, llm, settings=None)

    req = AgentChatRequest(message="Hi there", enable_custom_tools=True)
    res = await service.run_chat(project, req)

    assert res.finish_reason == "stop"
    assert res.message.content == "Hello! How can I help you today?"
    assert res.message.tool_calls is None


@pytest.mark.asyncio
async def test_agent_chat_returns_tool_calls_directive_for_client_mode(db_session: Session):
    project = Project(name="Agent Proj 2", api_key="sk_ag_2", client_key="pk_ag_2")
    db_session.add(project)
    db_session.commit()

    tool_svc = ProjectToolService(db_session)
    tool_svc.create_tool(
        project.id,
        ProjectToolCreate(
            name="get_stock",
            display_name="Get Stock",
            description="Check inventory stock",
            execution_mode="client_delegated",
            parameters_schema={
                "type": "object",
                "properties": {"sku": {"type": "string"}},
                "required": ["sku"],
            },
        ),
    )

    llm = FakeLlmClient(
        tool_calls=[
            ToolCall(id="call_999", name="get_stock", arguments={"sku": "SKU-100"})
        ]
    )

    service = AgentService(db_session, llm, settings=None)
    req = AgentChatRequest(message="What is the stock for SKU-100?", enable_custom_tools=True)
    res = await service.run_chat(project, req)

    assert res.finish_reason == "tool_calls"
    assert res.message.tool_calls is not None
    assert len(res.message.tool_calls) == 1
    assert res.message.tool_calls[0].function.name == "get_stock"
    assert '"SKU-100"' in res.message.tool_calls[0].function.arguments
