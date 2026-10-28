import json
import re


def main():
    with open("result.json", encoding="utf-8") as fh:
        result = json.load(fh)
    with open("corpus.json", encoding="utf-8") as fh:
        corpus = {d["id"]: d["text"] for d in json.load(fh)}
    claims = result["claims"]
    retrieved = set(result["retrieved"])
    checks = []

    uncited = [c["text"] for c in claims if not c["citations"]]
    checks.append(("every_claim_cited", not uncited, f"uncited: {uncited}" if uncited else "all claims cited"))

    bad_refs = [x for c in claims for x in c["citations"] if x not in retrieved]
    checks.append(("citations_were_retrieved", not bad_refs, f"bad refs: {bad_refs}" if bad_refs else "ok"))

    ungrounded = []
    for c in claims:
        evidence = " ".join(corpus.get(x, "") for x in c["citations"])
        missing = [n for n in re.findall(r"\d+(?:\.\d+)?%?", c["text"]) if n not in evidence]
        if missing or not c["citations"]:
            ungrounded.append(c["text"])
    checks.append(("figures_grounded_in_evidence", not ungrounded,
                   f"ungrounded: {ungrounded}" if ungrounded else "all figures appear in cited evidence"))

    answer = result["answer"]
    checks.append(("answers_the_question", "610 ms" in answer and len(claims) >= 2,
                   f"{len(claims)} claims; mentions key finding: {'610 ms' in answer}"))
    print(json.dumps([{"name": n, "passed": p, "detail": d} for n, p, d in checks]))


if __name__ == "__main__":
    main()
