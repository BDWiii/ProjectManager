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


class ReportAgent:
    def __init__(self, llm):
        self.llm = llm

        build_report = StateGraph(states.ReportState)

        build_report.add_node("reporter", self.report_node)

        build_report.set_entry_point("reporter")
        build_report.add_edge("reporter", END)

        self.report_agent = build_report.compile()

    def report_node(self, state: states.ReportState):
        # messages = [
        #     SystemMessage(content=prompts.REPORT_PROMPT),
        #     HumanMessage(
        #         content=f'{state.get("task", "")}\n\n{state.get("steps", "")}'
        #     ),
        # ]

        # response = self.llm.invoke(messages)
        full_report = state.get("report", "")
        return {
            "task": state.get("task", ""),
            "node_name": "report",
            "report": full_report,
        }
