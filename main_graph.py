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
from langgraph.types import Command, interrupt
import yaml
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from tools.search_tools import search_web
from agents import (
    states,
    estimator_agent,
    planner_agent,
    report_agent,
    schedule_agent,
    market_study_agent,
)

from utils import prompts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)


# ===================== Project Manager =====================


class ProjectManager(StateGraph):
    def __init__(self):
        self.llm = ChatOllama(model=config["model"])

        self.planner_agent = planner_agent.PlannerAgent(self.llm).planner_agent
        self.estimator_agent = estimator_agent.EstimatorAgent(self.llm).estimator_agent
        self.schedule_agent = schedule_agent.ScheduleAgent(self.llm).schedule_agent
        self.report_agent = report_agent.ReportAgent(self.llm).report_agent
        self.market_study_agent = market_study_agent.MarketStudyAgent(
            self.llm
        ).market_study_agent

        build_project_manager = StateGraph(states.MainState)

        build_project_manager.add_node("main_agent", self.main_agent_node)
        build_project_manager.add_node("planner_agent", self.planner_agent_node)
        build_project_manager.add_node("estimator_agent", self.estimator_agent_node)
        build_project_manager.add_node("schedule_agent", self.schedule_agent_node)
        build_project_manager.add_node("report_agent", self.report_agent_node)
        build_project_manager.add_node(
            "market_study_agent", self.market_study_agent_node
        )
        build_project_manager.add_node("chat", self.chat_node)
        build_project_manager.add_mode("interrupt", self.human_in_the_loop)

        build_project_manager.add_conditional_edges(
            "main_agent",
            self.decision,
            {
                "interrupt": "interrupt",
                "market_study_agent": "market_study_agent",
                "chat": "chat",
            },
        )

        build_project_manager.set_entry_point("main_agent")
        build_project_manager.add_edge("interrupt", "planner_agent")
        build_project_manager.add_edge("planner_agent", "estimator_agent")
        build_project_manager.add_edge("planner_agent", "schedule_agent")
        build_project_manager.add_edge("estimator_agent", "report_agent")
        build_project_manager.add_edge("market_study_agent", END)
        build_project_manager.add_edge("report_agent", END)

        self.project_manager = build_project_manager.compile()

    def main_agent_node(self, state: states.MainState):
        messages = [
            SystemMessage(content=prompts.MANAGER_PROMPT),
            HumanMessage(content=state.get("task", "")),
        ]
        response = self.llm.with_structured_output(states.MainRouter).invoke(messages)

        return {
            "task": state.get("task", ""),
            "node_name": "main_agent",
            "next_node": response.next_node,
        }

    def planner_agent_node(self, state: states.PlanState):
        planner_state = state["plan_state"]
        planner_state["task"] = state["task"]
        output = self.planner_agent.invoke(planner_state)

        return {
            "node_name": "planner_agent",
            "plan_state": output,
            "plan": output.get("plan", []),
            "retrieved_content": output.get("retrieved_content", []),
        }

    def estimator_agent_node(self, state: states.EstimatorState):
        estimator_state = state["estimator_state"]
        estimator_state["task"] = state["task"]
        estimator_state["steps"] = state["plan"]
        output = self.estimator_agent.invoke(estimator_state)

        return {
            "node_name": "estimator_agent",
            "estimator_state": output,
            "estimates": output.get("estimates", []),
        }

    def schedule_agent_node(self, state: states.ScheduleState):
        schedule_state = state["schedule_state"]
        schedule_state["task"] = state["task"]
        schedule_state["steps"] = state["plan"]
        output = self.schedule_agent.invoke(schedule_state)

        return {
            "node_name": "schedule_agent",
            "schedule_state": output,
            "schedule": output.get("schedule", ""),
        }

    def report_agent_node(self, state: states.ReportState):
        report_state = state["report_state"]
        report_state["task"] = state["task"]
        report_state["report"] = (
            f"{state.get("schedule", "")}\n\n Price estimations\n\n {state.get('estimates', [])}"
        )

        return {
            "node_name": "report_agent",
            "report_state": report_state,
            "report": report_state.get("report", ""),
        }

    def market_study_agent_node(self, state: states.MarketStudyState):
        market_study_state = state["market_study_state"]
        market_study_state["task"] = state["task"]
        output = self.market_study_agent.invoke(market_study_state)

        return {
            "node_name": "market_study_agent",
            "market_study_state": output,
            "market_study": output.get("market_study", ""),
            "retrieved_content": output.get("retrieved_content", []),
        }

    def chat_node(self, state: states.ChatState):
        messages = [
            SystemMessage(content=prompts.CHAT_PROMPT),
            HumanMessage(
                content=f'{state.get("task", "")}\n\n{state.get("content", "")}\n\n{state.get('retrieved_content')}'
            ),
        ]
        response = self.llm.invoke(messages)

        return {
            "chat": response.content,
        }

    def decision(self, state: states.MainState):
        messages = [
            SystemMessage(content=prompts.DECISION_PROMPT),
            HumanMessage(content=state.get("task", "")),
        ]
        response = self.llm.with_structured_output(states.MainRouter).invoke(messages)

        return {"next_node": response.next_node}

    def human_in_the_loop():

        return {}
