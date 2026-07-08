"""Debate orchestrator.

Runs the fixed-round debate across per-service agents and hands the full
transcript to the judge. Hard round cap enforced here — never allow the
debate to run unbounded.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from backend.agents.service_agent import ServiceAgent

MAX_ROUNDS = 4
CONVERGENCE_DELTA = 5  # stop early if top hypothesis confidence barely moves


@dataclass
class Orchestrator:
    agents: dict  # service -> ServiceAgent
    max_rounds: int = MAX_ROUNDS

    def run(self, logs_by_service: dict, candidate_edges: list) -> list:
        """logs_by_service: {service: [log entries]}. Returns transcript: list of rounds,
        each round a list of hypothesis dicts."""
        transcript = []
        prev_top_confidence = None

        best_incoming = self._best_incoming_source(candidate_edges)
        participants = [
            (service, agent) for service, agent in self.agents.items()
            if any(l["level"] in ("WARN", "ERROR") for l in logs_by_service.get(service, []))
        ]

        with ThreadPoolExecutor(max_workers=max(len(participants), 1)) as pool:
            # Round 1: propose, only agents whose service has anomalies participate.
            # Independent HTTP calls within a round run concurrently — this is what
            # keeps a 4-round debate to roughly one round-trip's worth of wall time
            # instead of (rounds x agents) round-trips.
            futures = {
                service: pool.submit(agent.propose, logs_by_service.get(service, []), best_incoming.get(service))
                for service, agent in participants
            }
            round_hyps = [futures[service].result() for service, _ in participants]
            transcript.append(round_hyps)

            for round_num in range(2, self.max_rounds + 1):
                all_prior = [h for r in transcript for h in r]
                futures = {
                    service: pool.submit(agent.respond, logs_by_service.get(service, []), all_prior, best_incoming.get(service))
                    for service, agent in participants
                }
                round_hyps = [futures[service].result() for service, _ in participants]
                transcript.append(round_hyps)

                top = self._top_hypothesis(transcript)
                if top:
                    if prev_top_confidence is not None and abs(top["confidence"] - prev_top_confidence) < CONVERGENCE_DELTA:
                        break
                    prev_top_confidence = top["confidence"]

        return transcript

    @staticmethod
    def _best_incoming_source(candidate_edges: list) -> dict:
        best = {}
        for edge in candidate_edges:
            target = edge["target"]
            if target not in best or edge["confidence"] > best[target][1]:
                best[target] = (edge["source"], edge["confidence"])
        return {k: v[0] for k, v in best.items()}

    @staticmethod
    def _top_hypothesis(transcript: list):
        all_hyps = [h for r in transcript for h in r]
        if not all_hyps:
            return None
        tally = defaultdict(list)
        for h in all_hyps:
            tally[h["target_service"]].append(h["confidence"])
        best_target = max(tally, key=lambda k: sum(tally[k]) / len(tally[k]))
        return {"target_service": best_target, "confidence": sum(tally[best_target]) / len(tally[best_target])}
