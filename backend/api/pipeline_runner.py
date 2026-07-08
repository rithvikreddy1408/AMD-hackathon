"""Live scenario pipeline: chaos replay + embedding graph + debate + judge,
publishing every step to Redis pub/sub channels for the WebSocket layer to
relay to the frontend.

Runs the embedding and debate steps inline in the API process rather than as
separate services — simpler to operate for a 72h build, and each piece
(chaos.player, embedding.service, agents.*) still works standalone via its
own CLI, so splitting into separate processes later is a config change, not
a rewrite.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import redis.asyncio as aioredis
import yaml

from backend.agents.fireworks_client import FireworksClient
from backend.agents.judge import Judge
from backend.agents.orchestrator import Orchestrator
from backend.agents.service_agent import ServiceAgent
from backend.embedding.service import EmbeddingEngine, GraphBuilder

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"

GRAPH_CHANNEL = "causal-graph-updates"
DEBATE_CHANNEL = "debate-events"
ROUND_PACING_SECONDS = 1.5


def load_scenario(scenario_id: str) -> dict:
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    return yaml.safe_load(open(path))


async def run_pipeline(scenario_id: str, redis_url: str, speed: float, mock: bool) -> None:
    scenario = load_scenario(scenario_id)
    r = aioredis.from_url(redis_url, decode_responses=True)

    await r.publish(DEBATE_CHANNEL, json.dumps({
        "type": "scenario_start", "scenario_id": scenario_id, "name": scenario["name"],
    }))

    engine = EmbeddingEngine()
    builder = GraphBuilder(engine=engine)
    logs_by_service = {s: [] for s in scenario["services"]}

    logs_sorted = sorted(scenario["logs"], key=lambda e: e["t"])
    start = time.monotonic()
    for entry in logs_sorted:
        target_elapsed = entry["t"] / speed
        wait = target_elapsed - (time.monotonic() - start)
        if wait > 0:
            await asyncio.sleep(wait)

        raw = {"scenario_id": scenario_id, **entry}
        logs_by_service[entry["service"]].append(entry)

        await r.publish("raw-logs", json.dumps(raw))
        await r.publish(GRAPH_CHANNEL, json.dumps({"type": "log", **raw}))

        edges = await asyncio.to_thread(builder.ingest, raw)
        for edge in edges:
            await r.publish(GRAPH_CHANNEL, json.dumps({"type": "edge", **edge}))

    await r.publish(DEBATE_CHANNEL, json.dumps({
        "type": "logs_complete", "embedding_stats": engine.stats(),
    }))

    agent_client = FireworksClient(model="accounts/fireworks/models/glm-5p2", mock=mock, timeout=60)
    judge_client = FireworksClient(model="accounts/fireworks/models/glm-5p2", mock=mock, timeout=60)
    agents = {
        s: ServiceAgent(service=s, client=agent_client, known_services=scenario["services"])
        for s in scenario["services"]
    }
    orchestrator = Orchestrator(agents=agents)

    transcript = await asyncio.to_thread(orchestrator.run, logs_by_service, builder.edges)

    for round_num, round_hyps in enumerate(transcript, start=1):
        await r.publish(DEBATE_CHANNEL, json.dumps({
            "type": "round", "round": round_num, "hypotheses": round_hyps,
        }))
        await asyncio.sleep(ROUND_PACING_SECONDS)

    judge = Judge(client=judge_client)
    verdict = await asyncio.to_thread(judge.decide, transcript, builder.edges, scenario["services"])

    await r.publish(DEBATE_CHANNEL, json.dumps({
        "type": "verdict",
        "agent_stats": agent_client.stats(),
        "judge_stats": judge_client.stats(),
        **verdict,
    }))

    gt = scenario["ground_truth"]
    await r.publish(DEBATE_CHANNEL, json.dumps({
        "type": "ground_truth",
        "root_cause_service": gt["root_cause_service"],
        "causal_chain": gt["causal_chain"],
        "explanation": gt["explanation"].strip(),
        "match": verdict["root_cause_service"] == gt["root_cause_service"],
    }))

    await r.aclose()
