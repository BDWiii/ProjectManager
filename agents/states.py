from typing import List, Dict, Literal, Annotated, Optional, TypedDict
from pydantic import BaseModel, Field
import operator

# ======================= Validation =======================


class MainRouter(BaseModel):
    next_node: Literal["interrupt", "market_study_agent", "chat"]


class Query(BaseModel):
    query: List[str]
    max_results: int = 3


# ======================= States =======================


class PlanState(TypedDict):
    task: str
    plan: List[str]
    node_name: str
    next_node: str
    retrieved_content: List[Dict]


class EstimatorState(TypedDict):
    task: str
    steps: List[str]
    node_name: str
    next_node: str
    retrieved_content: List[Dict]
    estimates: List[str]


class ScheduleState(TypedDict):
    task: str
    node_name: str
    steps: List[str]
    schedule: str


class ReportState(TypedDict):
    task: str
    node_name: str
    report: str


class MarketStudyState(TypedDict):
    task: str
    node_name: str
    next_node: str
    retrieved_content: List[Dict]
    market_study: str


class MainState(TypedDict):
    task: str
    node_name: str
    next_node: str
    plan: List[str]
    estimates: List[str]
    schedule: str
    retrieved_content: List[Dict]
    hitl: str
    # report: str
    end: str
    plan_state: PlanState
    schedule_state: ScheduleState
    estimator_state: EstimatorState
    report_state: ReportState
    market_study_state: MarketStudyState


# ==================== Initialization ====================
def _initialize_state() -> MainState:
    return {
        "task": "",
        "node_name": "",
        "next_node": "",
        "plan": [],
        "estimates": [],
        "schedule": "",
        "retrieved_content": [],
        "chat": "",
        "hitl": "",
        "end": "",
        "plan_state": {
            "task": "",
            "plan": [],
            "node_name": "",
            "next_node": "",
            "retrieved_content": [],
        },
        "schedule_state": {
            "task": "",
            "node_name": "",
            "steps": [],
            "schedule": "",
        },
        "estimator_state": {
            "task": "",
            "steps": [],
            "node_name": "",
            "next_node": "",
            "retrieved_content": [],
            "estimates": [],
        },
        "report_state": {
            "task": "",
            "node_name": "",
            "report": "",
        },
        "market_study_state": {
            "task": "",
            "node_name": "",
            "next_node": "",
            "retrieved_content": [],
            "market_study": "",
        },
    }
