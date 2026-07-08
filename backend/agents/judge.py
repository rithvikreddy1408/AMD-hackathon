"""Judge agent: arbitrates the full debate transcript into a final verdict.

Single Fireworks call against a larger model in live mode. Must always
return a verdict — falls back to a lowest-confidence heuristic guess rather
than refusing, matching the "always answer" project requirement.
"""
import sys
from collections import defaultdict

from backend.agents.fireworks_client import FireworksClient
from backend.agents.prompts import JUDGE_SYSTEM, JUDGE_USER, format_edges, format_transcript

FIX_SUGGESTIONS = {
    "pool exhausted": "Increase DB connection pool size and add backpressure/queueing limits.",
    "connection pool": "Increase DB connection pool size and add backpressure/queueing limits.",
    "cache eviction": "Fix TTL eviction job; add cache staleness monitoring and alerting.",
    "ttl eviction": "Fix TTL eviction job; add cache staleness monitoring and alerting.",
    "network unreachable": "Add DB replica failover and circuit breaker on the network partition path.",
    "db replica": "Add DB replica failover and circuit breaker on the network partition path.",
    "partition": "Add DB replica failover and circuit breaker on the network partition path.",
}
DEFAULT_FIX = "Add root-cause-service-specific rate limiting, timeout tuning, and alerting on the identified failure signature."


class Judge:
    def __init__(self, client: FireworksClient):
        self.client = client

    def decide(self, transcript: list, candidate_edges: list, known_services: list) -> dict:
        context = {"transcript": transcript, "candidate_edges": candidate_edges}
        system = JUDGE_SYSTEM.format(known_services=", ".join(known_services))
        user = JUDGE_USER.format(
            rounds=len(transcript),
            transcript=format_transcript(transcript),
            edges=format_edges(candidate_edges),
        )
        try:
            verdict = self.client.chat_json(system, user, mock_fn=self._mock_decide, mock_context=context, max_tokens=1200)
        except Exception as exc:
            print(f"[judge] decide call failed, falling back to heuristic: {exc}", file=sys.stderr)
            return self._fallback(transcript)
        return self._validate(verdict, known_services, transcript)

    @staticmethod
    def _validate(verdict: dict, known_services: list, transcript: list) -> dict:
        if verdict.get("root_cause_service") not in known_services:
            return Judge._fallback(transcript)
        verdict["causal_chain"] = [
            step for step in verdict.get("causal_chain", []) if step.get("service") in known_services
        ]
        return verdict

    @staticmethod
    def _mock_decide(context: dict) -> dict:
        transcript = context["transcript"]
        all_hyps = [h for r in transcript for h in r]
        if not all_hyps:
            return Judge._fallback(transcript)

        tally = defaultdict(list)
        evidence_by_target = defaultdict(list)
        for h in all_hyps:
            tally[h["target_service"]].append(h["confidence"])
            evidence_by_target[h["target_service"]].append((h["service"], h["evidence"]))

        root_cause = max(tally, key=lambda k: sum(tally[k]) / len(tally[k]))
        confidence_pct = min(round(sum(tally[root_cause]) / len(tally[root_cause])), 95)

        causal_chain = []
        seen = set()
        for service, evidence in evidence_by_target[root_cause]:
            if service in seen:
                continue
            seen.add(service)
            causal_chain.append({"service": service, "event": evidence})

        fix = DEFAULT_FIX
        for hyp_service, evidence in evidence_by_target[root_cause]:
            msg = evidence.lower()
            for marker, suggestion in FIX_SUGGESTIONS.items():
                if marker in msg:
                    fix = suggestion
                    break

        return {
            "root_cause_service": root_cause,
            "causal_chain": causal_chain,
            "confidence_pct": confidence_pct,
            "suggested_fix": fix,
        }

    @staticmethod
    def _fallback(transcript: list) -> dict:
        all_hyps = [h for r in transcript for h in r]
        if not all_hyps:
            return {
                "root_cause_service": "unknown",
                "causal_chain": [],
                "confidence_pct": 5,
                "suggested_fix": "Insufficient debate evidence; escalate to human on-call.",
            }
        weakest = min(all_hyps, key=lambda h: h["confidence"])
        return {
            "root_cause_service": weakest["target_service"],
            "causal_chain": [{"service": weakest["service"], "event": weakest["evidence"]}],
            "confidence_pct": max(weakest["confidence"] - 20, 5),
            "suggested_fix": DEFAULT_FIX,
        }
