"""End-to-end offline test harness: scenario -> embedding graph -> debate -> judge.

python3 -m backend.agents.run_debate scenarios/scenario_01.yaml
"""
import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agents.fireworks_client import FireworksClient
from backend.agents.judge import Judge
from backend.agents.orchestrator import Orchestrator
from backend.agents.service_agent import ServiceAgent
from backend.embedding.service import EmbeddingEngine, GraphBuilder


def build_candidate_edges(scenario: dict) -> list:
    engine = EmbeddingEngine()
    builder = GraphBuilder(engine=engine)
    for entry in sorted(scenario["logs"], key=lambda e: e["t"]):
        builder.ingest({"scenario_id": scenario["scenario_id"], **entry})
    return builder.edges


def group_logs_by_service(scenario: dict) -> dict:
    by_service = {s: [] for s in scenario["services"]}
    for entry in scenario["logs"]:
        by_service[entry["service"]].append(entry)
    return by_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full debate pipeline against a scenario")
    parser.add_argument("scenario_path", type=Path)
    parser.add_argument("--agent-model", default="accounts/fireworks/models/glm-5p2")
    parser.add_argument("--judge-model", default="accounts/fireworks/models/glm-5p2")
    parser.add_argument("--mock", action="store_true", help="force mock mode even if API key present")
    args = parser.parse_args()

    scenario = yaml.safe_load(open(args.scenario_path))
    print(f"=== {scenario['scenario_id']}: {scenario['name']} ===\n")

    candidate_edges = build_candidate_edges(scenario)
    print(f"embedding layer: {len(candidate_edges)} candidate edges\n")

    agent_client = FireworksClient(model=args.agent_model, mock=args.mock, timeout=60)
    judge_client = FireworksClient(model=args.judge_model, mock=args.mock, timeout=60)
    print(f"agent client mock={agent_client.mock}  judge client mock={judge_client.mock}\n")

    agents = {s: ServiceAgent(service=s, client=agent_client, known_services=scenario["services"]) for s in scenario["services"]}
    orchestrator = Orchestrator(agents=agents)

    logs_by_service = group_logs_by_service(scenario)
    transcript = orchestrator.run(logs_by_service, candidate_edges)

    for round_num, round_hyps in enumerate(transcript, start=1):
        print(f"--- Round {round_num} ---")
        for h in round_hyps:
            print(f"  {h['service']:<14} [{h['stance']:<7}] -> {h['target_service']:<14} "
                  f"conf={h['confidence']:<3} : {h['claim']}")
        print()

    judge = Judge(client=judge_client)
    verdict = judge.decide(transcript, candidate_edges, scenario["services"])

    print("=== JUDGE VERDICT ===")
    print(f"root cause:  {verdict['root_cause_service']}")
    print(f"confidence:  {verdict['confidence_pct']}%")
    print(f"fix:         {verdict['suggested_fix']}")
    print("causal chain:")
    for step in verdict["causal_chain"]:
        print(f"  - {step['service']}: {step['event']}")

    print("\n=== GROUND TRUTH ===")
    gt = scenario["ground_truth"]
    print(f"root cause:  {gt['root_cause_service']}")
    print(f"explanation: {gt['explanation'].strip()}")

    match = verdict["root_cause_service"] == gt["root_cause_service"]
    print(f"\nMATCH: {match}")

    print("\nbenchmarks:")
    print(" agent client:", agent_client.stats())
    print(" judge client:", judge_client.stats())

    sys.exit(0 if match else 1)


if __name__ == "__main__":
    main()
