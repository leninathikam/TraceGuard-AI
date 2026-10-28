"""Scenario B: a retrieval-augmented research agent.

Retrieves passages by keyword overlap and composes an answer as a list of claims with
citations. With include_background_knowledge enabled, it also appends "remembered"
facts that are not in the corpus, which produces an unsupported claim.
"""

import json
import re

from _tracer import Tracer

TASK = "What did the 2025 checkout latency study find?"

# Stale "parametric memory": plausible but not supported by any retrieved document.
BACKGROUND_KNOWLEDGE = [
    "The study also found that migrating checkout to gRPC cut p95 latency by 70%.",
]


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def retrieve(query, corpus, k):
    q = tokens(query)
    scored = sorted(corpus, key=lambda d: len(q & tokens(d["title"] + " " + d["text"])), reverse=True)
    return scored[:k]


def first_sentence(text):
    return re.split(r"(?<=\.)\s", text)[0]


def main():
    with open("answer_policy.json", encoding="utf-8") as fh:
        policy = json.load(fh)
    with open("corpus.json", encoding="utf-8") as fh:
        corpus = json.load(fh)
    tracer = Tracer("research-assistant", "research_agent", TASK, {
        "editable_files": ["answer_policy.json"],
        "agent_description": "Retrieves top_k passages by keyword overlap, turns the first sentence "
                             "of each into a cited claim, then optionally appends uncited claims from "
                             "built-in background knowledge (include_background_knowledge). "
                             "drop_uncited_claims removes claims without citations before answering.",
    })
    tracer.event("agent_start", "research-assistant", input={"task": TASK})
    docs = retrieve(TASK, corpus, policy["top_k"])
    tracer.event("retrieval", "keyword_search", input={"query": TASK, "top_k": policy["top_k"]},
                 output={"documents": docs})

    claims = [{"text": first_sentence(d["text"]), "citations": [d["id"]]} for d in docs]
    if policy.get("include_background_knowledge"):
        claims += [{"text": t, "citations": []} for t in BACKGROUND_KNOWLEDGE]
    tracer.event("agent_step", "compose_claims", output={"claims": claims})
    if policy.get("drop_uncited_claims"):
        claims = [c for c in claims if c["citations"]]

    answer = " ".join(c["text"] + "".join(f" [{x}]" for x in c["citations"]) for c in claims)
    tracer.event("output", "final_answer", output={"text": answer, "claims": claims})
    tracer.event("agent_end", "research-assistant", output={"status": "success"})
    # The agent believes it succeeded; the failure is silent.
    tracer.finish("success")
    with open("result.json", "w", encoding="utf-8") as fh:
        json.dump({"answer": answer, "claims": claims, "retrieved": [d["id"] for d in docs]}, fh)


if __name__ == "__main__":
    main()
