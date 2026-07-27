from typing import Annotated

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from agent.tools import check_policy, create_booking, search_travel, why_out_of_policy
from core.config import settings

TOOLS = [search_travel, check_policy, why_out_of_policy, create_booking]

SYSTEM_PROMPT = (
    "You are Wayfare, a corporate travel booking assistant. Search flights/hotels, "
    "always check_policy before booking, explain violations using why_out_of_policy "
    "when asked, and call create_booking only after the employee confirms a choice."
)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def build_agent_graph():
    model = ChatAnthropic(
        model="claude-sonnet-5", api_key=settings.anthropic_api_key
    ).bind_tools(TOOLS)

    def call_model(state: AgentState) -> AgentState:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *state["messages"]]
        return {"messages": [model.invoke(messages)]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
