"""FastAPI app: scenario control endpoints + WebSocket relay from Redis
pub/sub channels to the frontend.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import yaml
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, select

from backend.api.pipeline_runner import DEBATE_CHANNEL, GRAPH_CHANNEL, SCENARIOS_DIR, run_pipeline
from backend.auth.dependencies import get_current_user
from backend.auth.security import create_access_token, hash_password, verify_password
from backend.db.database import engine, get_session
from backend.db.models import ScenarioRun, User
from backend.worker.tasks import run_pipeline_task

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


# ── Lifespan: create DB tables on startup ──────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="Incident Mesh API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic request/response schemas ─────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Root / Health ──────────────────────────────────────────────────────────────
@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Incident Mesh API — navigate to /docs for the interactive API documentation.",
        "endpoints": ["/register", "/login", "/scenarios", "/scenario/{id}/start",
                      "/scenario/{id}/ground-truth", "/runs", "/ws/graph", "/ws/debate"],
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}


# ── Authentication ─────────────────────────────────────────────────────────────
@app.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == body.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token({"sub": user.email})
    return TokenResponse(access_token=token)


@app.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email)).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.email})
    return TokenResponse(access_token=token)


@app.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"email": current_user.email, "id": current_user.id, "is_active": current_user.is_active}


# ── Scenarios ──────────────────────────────────────────────────────────────────
@app.get("/scenarios")
def list_scenarios():
    out = []
    for path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        s = yaml.safe_load(open(path))
        out.append({"id": s["scenario_id"], "name": s["name"], "description": s["description"].strip()})
    return out


@app.get("/scenario/{scenario_id}/ground-truth")
def ground_truth(scenario_id: str):
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    if not path.exists():
        return {"error": "scenario not found"}
    s = yaml.safe_load(open(path))
    return s["ground_truth"]


@app.post("/scenario/{scenario_id}/start")
async def start_scenario(
    scenario_id: str,
    speed: float = 4.0,
    mock: bool = True,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Persist the run in the database
    run = ScenarioRun(scenario_id=scenario_id, status="pending", user_id=current_user.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    # Dispatch to Celery for resilient background execution
    run_pipeline_task.delay(scenario_id, run.id)

    return {"status": "queued", "scenario_id": scenario_id, "run_id": run.id}


# ── Run History ────────────────────────────────────────────────────────────────
@app.get("/runs")
def list_runs(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    runs = session.exec(
        select(ScenarioRun)
        .where(ScenarioRun.user_id == current_user.id)
        .order_by(ScenarioRun.created_at.desc())
    ).all()
    return [{"id": r.id, "scenario_id": r.scenario_id, "status": r.status, "created_at": r.created_at} for r in runs]


@app.get("/runs/{run_id}")
def get_run(
    run_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    run = session.get(ScenarioRun, run_id)
    if not run or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"id": run.id, "scenario_id": run.scenario_id, "status": run.status, "created_at": run.created_at}


# ── WebSocket relay ────────────────────────────────────────────────────────────
async def _relay(websocket: WebSocket, channel: str) -> None:
    await websocket.accept()
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()


@app.websocket("/ws/graph")
async def ws_graph(websocket: WebSocket) -> None:
    await _relay(websocket, GRAPH_CHANNEL)


@app.websocket("/ws/debate")
async def ws_debate(websocket: WebSocket) -> None:
    await _relay(websocket, DEBATE_CHANNEL)
