"""FastAPI app: scenario control endpoints + WebSocket relay from Redis
pub/sub channels to the frontend.
"""
from __future__ import annotations

import asyncio
import os

import redis.asyncio as aioredis
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api.pipeline_runner import DEBATE_CHANNEL, GRAPH_CHANNEL, SCENARIOS_DIR, run_pipeline

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

app = FastAPI(title="Incident Mesh API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
async def start_scenario(scenario_id: str, speed: float = 4.0, mock: bool = True):
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    if not path.exists():
        return {"error": "scenario not found"}
    asyncio.create_task(run_pipeline(scenario_id, REDIS_URL, speed=speed, mock=mock))
    return {"status": "started", "scenario_id": scenario_id, "speed": speed, "mock": mock}


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
