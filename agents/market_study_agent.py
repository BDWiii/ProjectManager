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


class MarketStudyAgent:
    """
    Search for trends and competitors, and generate a report.
    """

    def __init__(self, llm):
        self.llm = llm
        self.web_search_function = search_web

        build_market_study = StateGraph(states.MarketStudyState)

        build_market_study.add_node("search", self.search_node)
        build_market_study.add_node("market_studier", self.market_study_node)

        build_market_study.set_entry_point("search")
        build_market_study.add_edge("search", "market_studier")
        build_market_study.add_edge("market_studier", END)

        self.market_study_agent = build_market_study.compile()

    def search_node(self, state: states.MarketStudyState):
        messages = [
            SystemMessage(content=prompts.SEARCH_MARKET_PROMPT),
            HumanMessage(content=state.get("task", "")),
        ]
        search_queries = self.llm.with_structured_output(states.Query).invoke(messages)

        search_results = []
        for q in search_queries.query:
            response = self.web_search_function.invoke(
                q, max_results=search_queries.max_results
            )
            for item in response:
                search_results.append(
                    {
                        "url": item["url"],
                        "content": item["content"],
                    }
                )

        return {
            "node_name": "search",
            "retrieved_content": search_results,
            "task": state.get("task", ""),
        }

    def market_study_node(self, state: states.MarketStudyState):
        messages = [
            SystemMessage(content=prompts.MARKET_STUDY_PROMPT),
            HumanMessage(content=state.get("task", "")),
        ]
        response = self.llm.invoke(messages)

        return {
            "node_name": "market_studier",
            "market_study": response.content,
            "task": state.get("task", ""),
        }
