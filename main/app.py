import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
from main.main_graph import ProjectManager, RunProjectManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskRequest(BaseModel):
    task: str
    thread_id: Optional[str] = None


class AgentResponse(BaseModel):
    response: Any
    thread_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""

    global project_manager_instance

    logger.info("Starting project manager...")

    project_manager_instance = await ProjectManager.build()

    logger.info("Project manager started")

    yield

    logger.info("Shutting down project manager...")

    await project_manager_instance.close()

    logger.info("Project manager shutdown complete")


# Initializing the project manager app
app = FastAPI(
    title="Project Manager",
    lifespan=lifespan,
    description="Comprehensive Project Managing AI-solution",
    version="1.2.0",
)


@app.post("/project_manager/chat", response_model=AgentResponse)
async def run_agent(request: TaskRequest):
    """
    Main entry to chat with the project manager
    """

    if project_manager_instance is None:
        raise HTTPException(status_code=500, detail="Chatbot is not initialized")

    runner = RunProjectManager(project_manager_instance)
    input_text = request.task
    thread_id = request.thread_id

    if thread_id:
        runner.thread_id = thread_id
        runner.config = {"configurable": {"thread_id": thread_id}}
        result = await runner.existing_thread(input_text)
    else:
        result = await runner.new_thread(input_text)

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


@app.get("/project_manager/state/{thread_id}")
async def get_state(thread_id: str):
    """Get current state of the project manager"""

    if project_manager_instance is None:
        raise HTTPException(status_code=500, detail="Chatbot is not initialized")

    runner = RunProjectManager(project_manager_instance)
    try:
        snapshot = await runner.get_current_state(thread_id)
        return snapshot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "✅ ✅ ✅ !!"}


if __name__ == "__main__":
    import uvicorn

    # Run the server
    uvicorn.run("main.app:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
