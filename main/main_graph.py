import asyncio
import logging
import uuid

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.types import Command, interrupt
import yaml
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import aiosqlite


from agents.states import _initialize_state
from tools.search_tools import search_web
from agents import states
from agents.planner_agent import PlannerAgent
from agents.estimator_agent import EstimatorAgent
from agents.schedule_agent import ScheduleAgent
from agents.report_agent import ReportAgent
from agents.market_study_agent import MarketStudyAgent
from utils import prompts


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)


# ===================== Project Manager =====================


class ProjectManager(StateGraph):
    """
    Main Project Manager Agent-Orchestrator
    Factory pattern implementation to handle Async agents
    while maintaining resources at scale
    """

    def __init__(
        self,
        llm,
        planner_agent,
        estimator_agent,
        schedule_agent,
        report_agent,
        market_study_agent,
        # chatbot,
        conn,
        compiled_graph,
    ):
        self.llm = llm
        self.planner_agent = planner_agent
        self.estimator_agent = estimator_agent
        self.schedule_agent = schedule_agent
        self.report_agent = report_agent
        self.market_study_agent = market_study_agent
        # self.chatbot = chatbot
        self.conn = conn
        self.project_manager = compiled_graph

    @classmethod
    async def build(cls):
        llm = ChatOllama(model=config["model"])

        async def main_agent_node(state: states.MainState):
            messages = [
                SystemMessage(content=prompts.MANAGER_PROMPT),
                HumanMessage(content=state.get("task", "")),
            ]
            response = await llm.with_structured_output(states.MainRouter).ainvoke(
                messages
            )

            return {
                "task": state.get("task", ""),
                "node_name": "main_agent",
                "next_node": response.next_node,
            }

        async def planner_agent_node(state: states.MainState):
            planner_state = state["plan_state"]
            planner_state["task"] = (
                f"{state.get('task', '')}\n\n{state.get('hitl', '')}"
            )
            output = await planner_agent.ainvoke(planner_state)

            return {
                "node_name": "planner_agent",
                "plan_state": output,
                "plan": output.get("plan", []),
                "retrieved_content": output.get("retrieved_content", []),
            }

        async def estimator_agent_node(state: states.MainState):
            estimator_state = state["estimator_state"]
            estimator_state["task"] = state["task"]
            estimator_state["steps"] = state["plan"]
            output = await estimator_agent.ainvoke(estimator_state)

            return {
                "estimator_state": output,
                "estimates": output.get("estimates", []),
            }

        async def schedule_agent_node(state: states.MainState):
            schedule_state = state["schedule_state"]
            schedule_state["task"] = state["task"]
            schedule_state["steps"] = state["plan"]
            output = await schedule_agent.ainvoke(schedule_state)

            return {
                "schedule_state": output,
                "schedule": output.get("schedule", ""),
            }

        def report_agent_node(state: states.MainState):
            report_state = state["report_state"]
            report_state["task"] = state["task"]
            report_state["report"] = (
                f"{state.get("schedule", "")}\n\n Price estimations\n\n {state.get('estimates', [])}"
            )

            # Update history
            new_history = state.get("history", [])
            new_history.append({"role": "user", "content": state["task"]})
            new_history.append(
                {"role": "assistant", "content": report_state.get("report", "")}
            )

            return {
                "node_name": "report_agent",
                "report_state": report_state,
                "end": report_state.get("report", ""),
                "history": new_history,
            }

        async def market_study_agent_node(state: states.MainState):
            market_study_state = state["market_study_state"]
            market_study_state["task"] = state["task"]
            output = await market_study_agent.ainvoke(market_study_state)

            # update history
            new_history = state.get("history", [])
            new_history.append({"role": "user", "content": state["task"]})
            new_history.append(
                {"role": "assistant", "content": output.get("market_study", "")}
            )

            return {
                "node_name": "market_study_agent",
                "market_study_state": output,
                "market_study": output.get("market_study", ""),
                "end": output.get("market_study", ""),
                "retrieved_content": output.get("retrieved_content", []),
                "history": new_history,
            }

        async def chat_node(state: states.MainState):
            # Get last 5 messages
            history = state.get("history", [])[-5:]

            messages = [
                SystemMessage(content=prompts.CHAT_PROMPT),
                *[
                    (
                        HumanMessage(content=m["content"])
                        if m["role"] == "user"
                        else AIMessage(content=m["content"])
                    )
                    for m in history
                ],
                HumanMessage(content=f'{state.get("task", "")}'),
            ]
            response = await llm.ainvoke(messages)

            # Update history
            new_history = state.get("history", [])
            new_history.append({"role": "user", "content": state["task"]})
            new_history.append({"role": "assistant", "content": response.content})

            return {
                "node_name": "chat",
                "end": response.content,
                "task": state.get("task", ""),
                "history": new_history,
            }

        async def decision(state: states.MainState):
            messages = [
                SystemMessage(content=prompts.DECISION_PROMPT),
                HumanMessage(content=state.get("task", "")),
            ]
            response = await llm.with_structured_output(states.MainRouter).ainvoke(
                messages
            )

            return {"next_node": response.next_node}

        planner_agent = PlannerAgent(llm).planner_agent
        estimator_agent = EstimatorAgent(llm).estimator_agent
        schedule_agent = ScheduleAgent(llm).schedule_agent
        report_agent = ReportAgent(llm).report_agent
        market_study_agent = MarketStudyAgent(llm).market_study_agent

        build_project_manager = StateGraph(states.MainState)

        build_project_manager.add_node("main_agent", main_agent_node)
        build_project_manager.add_node("planner_agent", planner_agent_node)
        build_project_manager.add_node("estimator_agent", estimator_agent_node)
        build_project_manager.add_node("schedule_agent", schedule_agent_node)
        build_project_manager.add_node("report_agent", report_agent_node)
        build_project_manager.add_node("market_study_agent", market_study_agent_node)
        build_project_manager.add_node("chat", chat_node)

        build_project_manager.add_conditional_edges(
            "main_agent",
            lambda state: state.get("next_node", ""),
            {
                # "interrupt": "interrupt",
                "planner_agent": "planner_agent",
                "market_study_agent": "market_study_agent",
                "chat": "chat",
            },
        )

        build_project_manager.set_entry_point("main_agent")
        build_project_manager.add_edge("planner_agent", "estimator_agent")
        build_project_manager.add_edge("planner_agent", "schedule_agent")
        build_project_manager.add_edge("estimator_agent", "report_agent")
        build_project_manager.add_edge("market_study_agent", END)
        build_project_manager.add_edge("report_agent", END)

        conn = await aiosqlite.connect(
            "checkpoints/checkpoints.sqlite", check_same_thread=False
        )
        memory = AsyncSqliteSaver(conn)
        compile_kwargs = {"checkpointer": memory}

        compiled_graph = build_project_manager.compile(**compile_kwargs)

        return cls(
            llm,
            planner_agent,
            estimator_agent,
            schedule_agent,
            report_agent,
            market_study_agent,
            # chatbot,
            conn,
            compiled_graph,
        )

    async def close(self):
        if hasattr(self, "conn"):
            await self.conn.close()


class RunProjectManager:
    def __init__(self, agent: ProjectManager):
        self.agent = agent.project_manager
        self.threads = []
        self.thread_id = None
        self.config = {}

    async def new_thread(self, Input: str):
        self.thread_id = str(uuid.uuid4())
        self.config = {"configurable": {"thread_id": self.thread_id}}
        state = _initialize_state(Input)
        result = await self.agent.ainvoke(state, self.config)
        if result.get("pause"):
            return {
                "status": "paused",
                "thread_id": self.thread_id,
                "query": result.payload.get("query", "Human input required"),
            }

        return {"status": "running", "thread_id": self.thread_id, "output": result}

    async def existing_thread(self, Input: str):
        if not self.thread_id:
            raise ValueError("No existing thread_id to resume")
        snapshot = await self.agent.aget_state(self.config)
        state = dict(snapshot.values)
        original_task = state.get("task", "")
        updated = f"{original_task}\n\n{Input}"
        state["task"] = updated
        state["plan_state"]["task"] = updated

        command = Command(resume={"task": state["task"]})
        result = await self.agent.ainvoke(command, config=self.config)
        if isinstance(result, Command):
            return {
                "status": "paused",
                "thread_id": self.thread_id,
                "query": result.payload.get("query", "Human input requested"),
            }

        return {
            "status": "completed",
            "thread_id": self.thread_id,
            "output": result,
        }

    async def get_current_state(self, thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        return await self.agent.aget_state(config)


# test on new thread
if __name__ == "__main__":

    # Simulating HITL (two steps async calling)
    async def main():
        user_input = "I want to do finishing works to my room"

        agent = await ProjectManager.build()
        runner = RunProjectManager(agent)
        print("Starting new thread")

        response = await runner.new_thread(user_input)
        print("Agent paused for human input:")
        print(response)

        # Simulate Human-in-the-loop
        human_answer = "Full finishing works, open budget, and the flat is completely empty, i want modern style, and want to enjoy life."
        response = await runner.existing_thread(human_answer)
        print("Agent continued execution:")
        print(response)

        await agent.close()

    asyncio.run(main())
