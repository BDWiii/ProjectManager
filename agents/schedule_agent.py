import logging
from langchain_ollama import ChatOllama
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    ChatMessage,
    AnyMessage,
)
from langgraph.graph import StateGraph, END
from langgraph.types import Command
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from tools.search_tools import search_web
from agents import states
from utils import prompts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScheduleAgent:
    """
    Takes steps and makes a full schedule for the project including the steps that can be done in parallel.
    """

    def __init__(self, llm):
        self.llm = llm

        build_schedule = StateGraph(states.ScheduleState)

        build_schedule.add_node("scheduler", self.schedule_node)

        build_schedule.set_entry_point("scheduler")
        build_schedule.add_edge("scheduler", END)

        self.schedule_agent = build_schedule.compile()

    def schedule_node(self, state: states.ScheduleState):
        messages = [
            SystemMessage(content=prompts.SCHEDULER_PROMPT),
            HumanMessage(
                content=f'{state.get("task", "")}\n\n{state.get("steps", "")}'
            ),
        ]

        response = self.llm.invoke(messages)

        return {
            "task": state.get("task", ""),
            "node_name": "schedule",
            "schedule": response.content,
        }
