import json
import logging
from uuid import UUID
from sqlmodel import Session

from app.core.config import Settings
from app.models.project import Project
from app.models.project_tool import ProjectTool
from app.schemas.v1.agent import AgentChatRequest, AgentChatResponse, AgentFunctionCall, AgentMessage, FunctionDetail
from app.services.project_tool_service import ProjectToolService
from app.services.v2.llm_clients import BaseLlmClient, LlmResponse, ToolCall

logger = logging.getLogger(__name__)

DEFAULT_AGENT_SYSTEM_PROMPT = (
    "You are Scrutinize Intelligent Agent. You have access to custom project tools. "
    "When a user query requires executing an external tool or fetching live data, "
    "call the appropriate tool with precise JSON arguments. "
    "If no tool call is needed, answer directly and concisely."
)


class AgentService:
    """Agentic decision engine for evaluating intent, selecting tools, and processing execution loops."""

    def __init__(self, session: Session, llm_client: BaseLlmClient, settings: Settings):
        self.session = session
        self.llm_client = llm_client
        self.settings = settings
        self.tool_service = ProjectToolService(session)

    async def run_chat(self, project: Project, req: AgentChatRequest) -> AgentChatResponse:
        active_tools = []
        openai_tools = None

        if req.enable_custom_tools:
            active_tools = self.tool_service.get_active_tools(project.id)
            if active_tools:
                openai_tools = [self.tool_service.to_openai_tool(t) for t in active_tools]

        # Determine system prompt
        system_prompt = DEFAULT_AGENT_SYSTEM_PROMPT
        if project.settings and isinstance(project.settings, dict):
            overrides = project.settings.get("system_prompt_overrides", {})
            if overrides.get("agent"):
                system_prompt = overrides["agent"]

        # Case A: Handling client submitting tool results (multi-turn tool execution result)
        if req.messages and any(m.role == "tool" for m in req.messages):
            return await self._continue_tool_conversation(project, req, active_tools, openai_tools, system_prompt)

        # Case B: Initial user prompt
        user_query = req.message or ""
        model_name = self.settings.openai_model if hasattr(self.settings, "openai_model") else "gpt-4o-mini"
        if project.settings and isinstance(project.settings, dict):
            model_name = project.settings.get("decision_model") or model_name

        llm_resp: LlmResponse = self.llm_client.generate(
            model=model_name,
            system=system_prompt,
            user=user_query,
            tools=openai_tools,
        )

        # Check if LLM requested tool calls
        if llm_resp.tool_calls:
            return await self._handle_llm_tool_calls(
                project=project,
                llm_tool_calls=llm_resp.tool_calls,
                user_query=user_query,
                active_tools=active_tools,
                openai_tools=openai_tools,
                system_prompt=system_prompt,
                model_name=model_name,
                conversation_id=req.conversation_id,
            )

        # Direct textual answer
        return AgentChatResponse(
            finish_reason="stop",
            message=AgentMessage(role="assistant", content=llm_resp.content),
            conversation_id=req.conversation_id,
        )

    async def _handle_llm_tool_calls(
        self,
        project: Project,
        llm_tool_calls: list[ToolCall],
        user_query: str,
        active_tools: list[ProjectTool],
        openai_tools: list[dict] | None,
        system_prompt: str,
        model_name: str,
        conversation_id: str | None,
    ) -> AgentChatResponse:
        tools_by_name = {t.name: t for t in active_tools}

        formatted_tool_calls: list[AgentFunctionCall] = []
        server_executed_results: list[dict] = []

        for tc in llm_tool_calls:
            tool = tools_by_name.get(tc.name)
            if tool:
                # Validate parameters against JSON schema
                try:
                    self.tool_service.validate_arguments(tool, tc.arguments)
                except ValueError as err:
                    logger.warning(f"Tool arguments validation warning: {err}")

                # If execution_mode is server_webhook, execute HTTP request directly
                if tool.execution_mode == "server_webhook":
                    output = await self.tool_service.execute_webhook(
                        tool=tool,
                        arguments=tc.arguments,
                        secret_key=project.api_key,
                    )
                    server_executed_results.append({
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": output,
                    })
                else:
                    # Client-delegated mode
                    formatted_tool_calls.append(
                        AgentFunctionCall(
                            id=tc.id,
                            type="function",
                            function=FunctionDetail(
                                name=tc.name,
                                arguments=json.dumps(tc.arguments),
                            ),
                        )
                    )
            else:
                # Fallback for client execution
                formatted_tool_calls.append(
                    AgentFunctionCall(
                        id=tc.id,
                        type="function",
                        function=FunctionDetail(
                            name=tc.name,
                            arguments=json.dumps(tc.arguments),
                        ),
                    )
                )

        # If we have client-delegated tool calls to be executed by caller backend, return tool_calls directive
        if formatted_tool_calls:
            return AgentChatResponse(
                finish_reason="tool_calls",
                message=AgentMessage(
                    role="assistant",
                    content=None,
                    tool_calls=formatted_tool_calls,
                ),
                conversation_id=conversation_id,
            )

        # If all tool calls were server_webhook calls and executed automatically, synthesize final answer
        if server_executed_results:
            synthesized_user_prompt = f"User query: {user_query}\n\nTool execution results:\n"
            for res in server_executed_results:
                synthesized_user_prompt += f"Tool [{res['name']}]: {res['content']}\n"

            synth_resp = self.llm_client.generate(
                model=model_name,
                system=system_prompt,
                user=synthesized_user_prompt,
            )

            return AgentChatResponse(
                finish_reason="stop",
                message=AgentMessage(role="assistant", content=synth_resp.content),
                conversation_id=conversation_id,
            )

        return AgentChatResponse(
            finish_reason="stop",
            message=AgentMessage(role="assistant", content="Execution completed."),
            conversation_id=conversation_id,
        )

    async def _continue_tool_conversation(
        self,
        project: Project,
        req: AgentChatRequest,
        active_tools: list[ProjectTool],
        openai_tools: list[dict] | None,
        system_prompt: str,
    ) -> AgentChatResponse:
        """Synthesize final response after receiving tool results submitted by client app."""
        model_name = self.settings.openai_model if hasattr(self.settings, "openai_model") else "gpt-4o-mini"
        if project.settings and isinstance(project.settings, dict):
            model_name = project.settings.get("decision_model") or model_name

        tool_messages_text = ""
        for m in req.messages or []:
            if m.role == "tool":
                tool_messages_text += f"Tool Call [{m.name or m.tool_call_id}]: {m.content}\n"
            elif m.role == "user" and m.content:
                tool_messages_text += f"User query context: {m.content}\n"

        prompt = (
            f"Tool execution results received:\n{tool_messages_text}\n"
            "Please synthesize a clear, helpful final response for the user based on these results."
        )

        synth_resp = self.llm_client.generate(
            model=model_name,
            system=system_prompt,
            user=prompt,
        )

        return AgentChatResponse(
            finish_reason="stop",
            message=AgentMessage(role="assistant", content=synth_resp.content),
            conversation_id=req.conversation_id,
        )
