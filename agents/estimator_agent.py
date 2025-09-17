import asyncio
import logging
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END

from tools.search_tools import search_web
from agents import states
from utils import prompts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EstimatorAgent:
    """
    Takes a plan and estimates the cost for each step and the total cost.
    """

    def __init__(self, llm):
        self.llm = llm
        self.web_search_function = search_web

        build_estimator = StateGraph(states.EstimatorState)

        build_estimator.add_node("search", self.search_node)
        build_estimator.add_node("estimator", self.estimator_node)

        build_estimator.set_entry_point("search")
        build_estimator.add_edge("search", "estimator")
        build_estimator.add_edge("estimator", END)

        self.estimator_agent = build_estimator.compile()

    async def search_node(self, state: states.EstimatorState):
        messages = [
            SystemMessage(content=prompts.COST_SEARCH_PROMPT),
            HumanMessage(content=state.get("task", "")),
        ]
        search_queries = await self.llm.with_structured_output(states.Query).ainvoke(
            messages
        )

        search_results = []

        tasks = [
            self.web_search_function.ainvoke(
                {"query": q, "max_results": search_queries.max_results}
            )
            for q in search_queries.query
        ]
        responses = await asyncio.gather(*tasks)

        for response in responses:
            for item in response:
                search_results.append(
                    {
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                    }
                )

        return {
            "node_name": "search",
            "retrieved_content": search_results,
            "task": state.get("task", ""),
        }

    async def estimator_node(self, state: states.EstimatorState):
        messages = [
            SystemMessage(content=prompts.ESTIMATOR_PROMPT),
            HumanMessage(content=state.get("task", "")),
        ]
        response = await self.llm.ainvoke(messages)

        return {
            "task": state.get("task", ""),
            "node_name": "estimator",
            "next_node": state.get("next_node", ""),
            "estimates": response.content,
            "retrieved_content": state.get("retrieved_content", []),
        }


#
