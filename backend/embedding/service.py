"""Local embedding + causal graph builder.

Runs on the AMD GPU (ROCm exposes as torch device 'cuda'). Consumes raw log
lines, embeds each message, and correlates anomalous lines across services
within a sliding time window to emit candidate causal graph edges.

Two run modes:
  --offline <scenario.yaml>   read a scenario file directly, no Redis needed.
                              Used for local testing and GPU benchmarking.
  (default)                   subscribe to Redis pub/sub channel "raw-logs",
                              publish edges to "causal-graph-updates".
"""
import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sentence_transformers import SentenceTransformer

WINDOW_SECONDS = 12
SIMILARITY_THRESHOLD = 0.35
ANOMALOUS_LEVELS = {"WARN", "ERROR"}


class EmbeddingEngine:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        device = self._pick_device()
        self.model = SentenceTransformer(model_name, device=device)
        self.device = device
        self.total_lines = 0
        self.total_seconds = 0.0

    @staticmethod
    def _pick_device() -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    def embed(self, text: str):
        start = time.perf_counter()
        vector = self.model.encode(text)
        elapsed = time.perf_counter() - start
        self.total_lines += 1
        self.total_seconds += elapsed
        return vector, elapsed

    def stats(self) -> dict:
        avg_ms = (self.total_seconds / self.total_lines * 1000) if self.total_lines else 0.0
        return {"device": self.device, "lines_embedded": self.total_lines, "avg_ms_per_line": round(avg_ms, 3)}


@dataclass
class LogEvent:
    scenario_id: str
    service: str
    t: float
    level: str
    message: str
    embedding: object = None

    @property
    def is_anomalous(self) -> bool:
        return self.level in ANOMALOUS_LEVELS


@dataclass
class GraphBuilder:
    engine: EmbeddingEngine
    window_seconds: float = WINDOW_SECONDS
    similarity_threshold: float = SIMILARITY_THRESHOLD
    buffer: list = field(default_factory=list)
    edges: list = field(default_factory=list)

    def ingest(self, raw: dict) -> list:
        vector, _ = self.engine.embed(raw["message"])
        event = LogEvent(
            scenario_id=raw["scenario_id"],
            service=raw["service"],
            t=raw["t"],
            level=raw["level"],
            message=raw["message"],
            embedding=vector,
        )
        self.buffer.append(event)
        self._prune(event.t)

        new_edges = []
        if event.is_anomalous:
            new_edges = self._correlate(event)
            self.edges.extend(new_edges)
        return new_edges

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self.buffer = [e for e in self.buffer if e.t >= cutoff]

    def _correlate(self, effect: LogEvent) -> list:
        found = []
        for cause in self.buffer:
            if cause is effect:
                continue
            if cause.service == effect.service:
                continue
            if not cause.is_anomalous:
                continue
            dt = effect.t - cause.t
            if dt <= 0 or dt > self.window_seconds:
                continue

            sim = self._cosine(cause.embedding, effect.embedding)
            time_decay = 1.0 - (dt / self.window_seconds)
            confidence = round(max(0.0, sim) * 0.6 + time_decay * 0.4, 3)
            if sim < self.similarity_threshold and time_decay < 0.5:
                continue

            found.append({
                "source": cause.service,
                "target": effect.service,
                "confidence": confidence,
                "similarity": round(float(sim), 3),
                "lag_seconds": dt,
                "evidence_source": cause.message,
                "evidence_target": effect.message,
            })
        return found

    @staticmethod
    def _cosine(a, b) -> float:
        import numpy as np
        a, b = np.asarray(a), np.asarray(b)
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        return float(a.dot(b) / denom) if denom else 0.0


def run_offline(scenario_path: Path) -> None:
    scenario = yaml.safe_load(open(scenario_path))
    engine = EmbeddingEngine()
    builder = GraphBuilder(engine=engine)

    print(f"scenario: {scenario['scenario_id']}  device: {engine.device}")
    for entry in sorted(scenario["logs"], key=lambda e: e["t"]):
        raw = {"scenario_id": scenario["scenario_id"], **entry}
        edges = builder.ingest(raw)
        for edge in edges:
            print(f"  edge: {edge['source']} -> {edge['target']}  "
                  f"conf={edge['confidence']}  lag={edge['lag_seconds']}s  sim={edge['similarity']}")

    print("\nbenchmark:", engine.stats())
    print(f"total edges found: {len(builder.edges)}")
    print("ground truth root cause:", scenario["ground_truth"]["root_cause_service"])

    inferred_sources = {e["source"] for e in builder.edges}
    if scenario["ground_truth"]["root_cause_service"] in inferred_sources:
        print("root cause service appears as an edge source: MATCH")
    else:
        print("root cause service NOT found as edge source: check thresholds")


def run_live(redis_host: str, redis_port: int) -> None:
    import redis
    r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    pubsub = r.pubsub()
    pubsub.subscribe("raw-logs")

    engine = EmbeddingEngine()
    builder = GraphBuilder(engine=engine)
    print(f"embedding service live, device={engine.device}, listening on raw-logs")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue
        raw = json.loads(message["data"])
        edges = builder.ingest(raw)
        for edge in edges:
            r.publish("causal-graph-updates", json.dumps(edge))
            print(f"published edge: {edge['source']} -> {edge['target']} conf={edge['confidence']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local embedding + causal graph builder")
    parser.add_argument("--offline", type=Path, help="scenario YAML to run offline, no Redis")
    parser.add_argument("--redis-host", default="localhost")
    parser.add_argument("--redis-port", type=int, default=6379)
    args = parser.parse_args()

    if args.offline:
        run_offline(args.offline)
    else:
        run_live(args.redis_host, args.redis_port)


if __name__ == "__main__":
    main()
