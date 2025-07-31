from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
from main.main_graph import RunProjectManager

app = FastAPI()
runner = RunProjectManager()


class TaskRequest(BaseModel):
    task: str
    thread_id: Optional[str] = None


class AgentResponse(BaseModel):
    response: Any
    thread_id: str


@app.post("/run", response_model=AgentResponse)
async def run_agent(request: TaskRequest):

    input_text = request.task
    thread_id = request.thread_id

    if thread_id:
        runner.thread_id = thread_id
        runner.config = {"configurable": {"thread_id": thread_id}}
        result = runner.existing_thread(input_text)
    else:
        result = runner.new_thread(input_text)

    status = result["status"]
    if status == "paused":
        return {
            "response": result.get("query", "Human input required"),
            "thread_id": result["thread_id"],
        }
    elif status in {"running", "completed"}:
        return {
            "response": result.get("output", "No output available"),
            "thread_id": result["thread_id"],
        }
    else:
        raise HTTPException(status_code=500, detail="Unknown status returned by agent.")


@app.get("/state/{thread_id}")
async def get_state(thread_id: str):
    try:
        snapshot = runner.get_current_state(thread_id)
        return snapshot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "✅ ✅ ✅"}
