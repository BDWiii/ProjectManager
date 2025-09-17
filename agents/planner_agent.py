import asyncio
import logging
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.types import Command, interrupt

from tools.search_tools import search_web
from agents import states
from utils import prompts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ===================== Search Agent =====================


class PlannerAgent:
    """
    Search -> Generate a plan with clear steps.
    """

    def __init__(self, llm):
        self.llm = llm
        self.web_search_function = search_web

        build_search = StateGraph(states.PlanState)

        build_search.add_node("search", self.search_node)
        build_search.add_node("planner", self.planner_node)
        build_search.add_node("interrupt", self.human_in_the_loop)

        build_search.set_entry_point("interrupt")
        build_search.add_edge("interrupt", "search")
        build_search.add_edge("search", "planner")
        build_search.add_edge("planner", END)

        self.planner_agent = build_search.compile()

    async def human_in_the_loop(self, state: states.PlanState):
        messages = [
            SystemMessage(content=prompts.HITL_PROMPT),
            HumanMessage(content=state.get("task", "")),
        ]
        question_to_human = await self.llm.ainvoke(messages)

        return interrupt({"query": question_to_human.content})

    async def search_node(self, state: states.PlanState):
        messages = [
            SystemMessage(content=prompts.SEARCH_PROMPT),
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

    async def planner_node(self, state: states.PlanState):
        formatted_retrieved_content = []
        for item in state["retrieved_content"]:
            formatted = f'url: {item["url"]}\ncontent: {item["content"]}'
            formatted_retrieved_content.append(formatted)

        formatted_content_string = "\n\n".join(formatted_retrieved_content)

        messages = [
            SystemMessage(content=prompts.PLANNER_PROMPT),
            HumanMessage(
                content=f'{state.get("task", "")}\n\n{formatted_content_string}'
            ),
        ]
        response = await self.llm.ainvoke(messages)

        return {
            "node_name": "planner",
            "plan": [response.content],
            "task": state.get("task", ""),
            "retrieved_content": state.get("retrieved_content", []),
        }
