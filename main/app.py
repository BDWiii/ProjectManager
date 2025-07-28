from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
from main.main_graph import RunProjectManager

app = FastAPI()
runner = RunProjectManager

class TaskRequest(BaseModel):
    task: str
    thread_id: Optional[str] = None
    
class AgentResponse(BaseModel):
    final_output: Any
    thread_id: str