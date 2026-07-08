"""Per-service debate agent.

Each agent only ever sees its own service's logs. It proposes a causal
hypothesis in round 1, then attacks/supports other agents' hypotheses in
subsequent rounds. Uses FireworksClient.chat_json, which transparently runs
either the real Fireworks API or the deterministic offline mock.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from backend.agents.fireworks_client import FireworksClient
from backend.agents.prompts import (
    AGENT_PROPOSE_USER,
    AGENT_RESPOND_USER,
    AGENT_SYSTEM,
    format_hypotheses,
    format_logs,
)

SELF_CAUSE_MARKERS = [
    "pool exhausted", "connection pool", "cache eviction", "network unreachable",
    "db replica", "overloaded", "backlogged", "exhausted", "ttl eviction",
    "unreachable", "partition",
]


@dataclass
class ServiceAgent:
    service: str
    client: FireworksClient
    known_services: list

    def propose(self, own_logs: list, candidate_source: str | None) -> dict:
        context = {
            "service": self.service,
            "own_logs": own_logs,
            "known_services": self.known_services,
            "candidate_source": candidate_source,
        }
        system = AGENT_SYSTEM.format(service=self.service, known_services=", ".join(self.known_services))
        user = AGENT_PROPOSE_USER.format(own_logs=format_logs(own_logs))
        try:
            hyp = self.client.chat_json(system, user, mock_fn=self._mock_propose, mock_context=context, max_tokens=1200)
        except Exception as exc:  # a live demo must never crash on one flaky call
            print(f"[{self.service}] propose call failed, falling back to heuristic: {exc}", file=sys.stderr)
            hyp = self._mock_propose(context)
        return self._validate(hyp)

    def respond(self, own_logs: list, hypotheses: list, candidate_source: str | None) -> dict:
        context = {
            "service": self.service,
            "own_logs": own_logs,
            "known_services": self.known_services,
            "candidate_source": candidate_source,
            "hypotheses": hypotheses,
        }
        system = AGENT_SYSTEM.format(service=self.service, known_services=", ".join(self.known_services))
        user = AGENT_RESPOND_USER.format(
            own_logs=format_logs(own_logs), hypotheses=format_hypotheses(hypotheses)
        )
        try:
            hyp = self.client.chat_json(system, user, mock_fn=self._mock_respond, mock_context=context, max_tokens=1200)
        except Exception as exc:  # a live demo must never crash on one flaky call
            print(f"[{self.service}] respond call failed, falling back to heuristic: {exc}", file=sys.stderr)
            hyp = self._mock_respond(context)
        return self._validate(hyp)

    def _validate(self, hyp: dict) -> dict:
        if hyp.get("target_service") not in self.known_services:
            hyp["target_service"] = self.service
        return hyp

    # -- deterministic offline heuristic, mirrors what a real model should output --

    def _base_hypothesis(self, context: dict) -> dict:
        service = context["service"]
        anomalous = [l for l in context["own_logs"] if l["level"] in ("WARN", "ERROR")]
        if not anomalous:
            return {
                "service": service, "stance": "propose", "target_service": service,
                "claim": "no anomalies observed this round", "evidence": "n/a", "confidence": 5,
            }

        worst = max(anomalous, key=lambda l: (l["level"] == "ERROR", l["t"]))
        msg = worst["message"].lower()

        if any(marker in msg for marker in SELF_CAUSE_MARKERS):
            confidence = min(60 + 5 * len(anomalous), 95)
            return {
                "service": service, "stance": "propose", "target_service": service,
                "claim": f"{service} anomaly is self-originating (internal resource exhaustion)",
                "evidence": worst["message"], "confidence": confidence,
            }

        for other in context["known_services"]:
            if other != service and other in msg:
                return {
                    "service": service, "stance": "propose", "target_service": other,
                    "claim": f"{service} anomalies mention {other} directly in evidence",
                    "evidence": worst["message"], "confidence": 55,
                }

        if context.get("candidate_source"):
            return {
                "service": service, "stance": "propose", "target_service": context["candidate_source"],
                "claim": f"{service} anomalies temporally follow {context['candidate_source']} (embedding correlation)",
                "evidence": worst["message"], "confidence": 40,
            }

        return {
            "service": service, "stance": "propose", "target_service": service,
            "claim": f"{service} shows anomalies with unclear origin",
            "evidence": worst["message"], "confidence": 25,
        }

    def _mock_propose(self, context: dict) -> dict:
        return self._base_hypothesis(context)

    def _mock_respond(self, context: dict) -> dict:
        own = self._base_hypothesis(context)
        hypotheses = context["hypotheses"]
        if not hypotheses:
            return own

        top = max(hypotheses, key=lambda h: h["confidence"])
        if own["target_service"] == top["target_service"]:
            own["stance"] = "support"
            own["confidence"] = min(own["confidence"] + 15, 95)
            own["claim"] = f"corroborates: {own['claim']}"
        else:
            own["stance"] = "attack"
            own["claim"] = f"disputes '{top['target_service']}' theory: {own['claim']}"
        return own
