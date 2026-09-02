from typing import Any, List, Optional
from pydantic import BaseModel, Field


class FunctionDetail(BaseModel):
    name: str
    arguments: str  # JSON-encoded string or object representation per OpenAI standard


class AgentFunctionCall(BaseModel):
    id: str
    type: str = "function"
    function: FunctionDetail


class AgentMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[AgentFunctionCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class AgentChatRequest(BaseModel):
    message: Optional[str] = Field(default=None, description="User query prompt for initial turn")
    conversation_id: Optional[str] = Field(default=None, description="Optional conversation identifier")
    enable_custom_tools: bool = Field(default=True, description="Whether to enable project-scoped custom tools")
    messages: Optional[List[AgentMessage]] = Field(
        default=None,
        description="Optional full conversation thread or tool result submissions for multi-turn execution",
    )


class AgentChatResponse(BaseModel):
    finish_reason: str = Field(..., description="'stop' or 'tool_calls'")
    message: AgentMessage
    conversation_id: Optional[str] = None
