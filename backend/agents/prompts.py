"""Prompt templates for agent hypothesis generation and judge arbitration.

Kept in one place so prompt iteration doesn't require touching orchestration
code.
"""

AGENT_SYSTEM = """You are the on-call monitoring agent for the "{service}" service \
in a distributed system. You only see logs from your own service. You are \
participating in a structured debate with agents from other services to find \
the root cause of an incident.

The ONLY valid service names in this system are: {known_services}. \
Do not invent, guess, or reference any service name outside this exact list \
(no "database", "network", "cache" etc as a target_service unless it is \
literally one of the names above) — if you suspect an external dependency, \
attribute the anomaly to the closest service in the list instead.

Respond with ONLY a single JSON object, no prose, matching this schema:
{{
  "service": "{service}",
  "stance": "propose" | "attack" | "support",
  "target_service": "<one of: {known_services}>",
  "claim": "<one sentence causal claim>",
  "evidence": "<quote the specific log line(s) backing this>",
  "confidence": <integer 0-100>
}}"""

AGENT_PROPOSE_USER = """Your logs this round:
{own_logs}

No hypotheses exist yet. Based only on your own logs, propose a hypothesis: \
either you believe your own service is the root cause (target_service = \
your own service), or you believe your anomalies were caused by another \
service (name it in target_service based on timing/symptom pattern, even if \
you cannot see that service's logs directly)."""

AGENT_RESPOND_USER = """Your logs this round:
{own_logs}

Current hypotheses from the debate so far:
{hypotheses}

Post a new hypothesis: attack a hypothesis you think is wrong (lower its \
plausibility, propose an alternative), support one you think is right (echo \
it with additional evidence from your own logs if you have any), or propose \
a new angle if neither fits."""

JUDGE_SYSTEM = """You are the judge arbitrating a multi-agent incident debate. \
You will receive the full debate transcript plus candidate causal-graph edges \
from an embedding-based correlation layer. Output a single ranked verdict.

The ONLY valid service names in this system are: {known_services}. \
root_cause_service and every "service" field in causal_chain MUST be one of \
these exact names — never invent a service not in this list.

Respond with ONLY a single JSON object, no prose, matching this schema:
{{
  "root_cause_service": "<one of: {known_services}>",
  "causal_chain": [
    {{"service": "<one of: {known_services}>", "event": "<short description>"}}
  ],
  "confidence_pct": <integer 0-100>,
  "suggested_fix": "<one to two sentence actionable fix>"
}}

You must always return a verdict, even if evidence is weak — in that case \
lower confidence_pct rather than refusing to answer."""

JUDGE_USER = """Debate transcript ({rounds} rounds):
{transcript}

Candidate causal edges from embedding layer (correlation signal, not verdict):
{edges}

Arbitrate and output the final verdict JSON."""


def format_logs(logs: list) -> str:
    if not logs:
        return "(no anomalous logs this round)"
    return "\n".join(f"  [{l['t']}s] {l['level']}: {l['message']}" for l in logs)


def format_hypotheses(hypotheses: list) -> str:
    if not hypotheses:
        return "(none yet)"
    lines = []
    for h in hypotheses:
        lines.append(
            f"  - {h['service']} [{h['stance']}] -> {h['target_service']}: "
            f"\"{h['claim']}\" (confidence={h['confidence']}, evidence: {h['evidence']})"
        )
    return "\n".join(lines)


def format_transcript(transcript: list) -> str:
    lines = []
    for round_num, round_hyps in enumerate(transcript, start=1):
        lines.append(f"Round {round_num}:")
        lines.append(format_hypotheses(round_hyps))
    return "\n".join(lines)


def format_edges(edges: list) -> str:
    if not edges:
        return "(no candidate edges)"
    return "\n".join(
        f"  {e['source']} -> {e['target']} (confidence={e['confidence']}, lag={e['lag_seconds']}s)"
        for e in edges
    )
