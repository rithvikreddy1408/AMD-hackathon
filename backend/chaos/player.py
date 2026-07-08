"""Chaos scenario player.

Reads a scenario YAML and replays its log lines onto per-service Redis
Streams at the recorded relative timing (scaled by scenario `speed`).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import redis
import yaml

STREAM_PREFIX = "logs"


def load_scenario(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def stream_key(service: str) -> str:
    return f"{STREAM_PREFIX}:{service}"


def play(scenario: dict, r: redis.Redis, speed_override: float | None = None) -> None:
    speed = speed_override or scenario.get("speed", 1.0)
    logs = sorted(scenario["logs"], key=lambda entry: entry["t"])
    scenario_id = scenario["scenario_id"]

    start = time.monotonic()
    for entry in logs:
        target_elapsed = entry["t"] / speed
        wait = target_elapsed - (time.monotonic() - start)
        if wait > 0:
            time.sleep(wait)

        payload = {
            "scenario_id": scenario_id,
            "service": entry["service"],
            "t": entry["t"],
            "level": entry["level"],
            "message": entry["message"],
        }
        r.xadd(stream_key(entry["service"]), {"data": json.dumps(payload)})
        r.publish("raw-logs", json.dumps(payload))
        print(f"[{entry['t']:>4}s] {entry['service']:<14} {entry['level']:<5} {entry['message']}")

    print(f"scenario {scenario_id} replay complete, {len(logs)} log lines emitted")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a chaos scenario into Redis")
    parser.add_argument("scenario_path", type=Path)
    parser.add_argument("--redis-host", default="localhost")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--speed", type=float, default=None, help="override scenario speed multiplier")
    args = parser.parse_args()

    scenario = load_scenario(args.scenario_path)
    r = redis.Redis(host=args.redis_host, port=args.redis_port, decode_responses=True)
    play(scenario, r, speed_override=args.speed)


if __name__ == "__main__":
    main()
