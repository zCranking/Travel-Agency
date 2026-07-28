from typing import Annotated

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from agent.tools import (
    check_disruptions,
    check_policy,
    create_booking,
    search_travel,
    why_out_of_policy,
)
from core.config import settings

BOOKING_TOOLS = [search_travel, check_policy, create_booking]
POLICY_TOOLS = [check_policy, why_out_of_policy]
DISRUPTION_TOOLS = [check_disruptions]

BOOKING_PROMPT = (
    "You are Wayfare's booking specialist. Search flights/hotels, always "
    "check_policy before booking, and call create_booking only after the "
    "employee confirms a choice."
)
POLICY_PROMPT = (
    "You are Wayfare's policy specialist. Answer 'is this in policy' and "
    "'why' questions thoroughly, citing the policy document via "
    "why_out_of_policy whenever you can. You do not book anything."
)
DISRUPTION_PROMPT = (
    "You are Wayfare's disruption specialist. Use check_disruptions to look "
    "up whether a trip's flights are delayed or cancelled, and explain "
    "clearly what changed. You do not book anything new."
)

_DISRUPTION_KEYWORDS = ("disrupt", "delay", "delayed", "cancel", "rebook", "flight status")
_POLICY_KEYWORDS = ("why", "policy", "compliant", "allowed", "in-policy", "in policy", "out of policy")


def classify_intent(text: str) -> str:
    """Cheap keyword routing — no extra LLM call needed to pick a
    specialist. Order matters: disruption keywords are checked before
    policy keywords since 'rebook' could otherwise look booking-flavored."""
    lowered = text.lower()
    if any(k in lowered for k in _DISRUPTION_KEYWORDS):
        return "disruption"
    if any(k in lowered for k in _POLICY_KEYWORDS):
        return "policy"
    return "booking"


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        role = getattr(message, "type", None) or (
            message.get("role") if isinstance(message, dict) else None
        )
        if role in ("human", "user"):
            content = getattr(message, "content", None) or (
                message.get("content") if isinstance(message, dict) else ""
            )
            return content if isinstance(content, str) else ""
    return ""


def _route(state: AgentState) -> AgentState:
    return state


def _route_edge(state: AgentState) -> str:
    return classify_intent(_last_human_text(state))


def _make_specialist(tools: list, system_prompt: str):
    model = ChatAnthropic(model="claude-sonnet-5", api_key=settings.anthropic_api_key).bind_tools(tools)

    def call_model(state: AgentState) -> AgentState:
        messages = [{"role": "system", "content": system_prompt}, *state["messages"]]
        return {"messages": [model.invoke(messages)]}

    return call_model


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("route", _route)
    graph.set_entry_point("route")

    specialists = {
        "booking": (BOOKING_TOOLS, BOOKING_PROMPT),
        "policy": (POLICY_TOOLS, POLICY_PROMPT),
        "disruption": (DISRUPTION_TOOLS, DISRUPTION_PROMPT),
    }

    routes = {}
    for name, (tools, prompt) in specialists.items():
        agent_node = f"{name}_agent"
        tools_node = f"{name}_tools"
        graph.add_node(agent_node, _make_specialist(tools, prompt))
        graph.add_node(tools_node, ToolNode(tools))
        graph.add_conditional_edges(agent_node, tools_condition, {"tools": tools_node, END: END})
        graph.add_edge(tools_node, agent_node)
        routes[name] = agent_node

    graph.add_conditional_edges("route", _route_edge, routes)
    return graph.compile()
