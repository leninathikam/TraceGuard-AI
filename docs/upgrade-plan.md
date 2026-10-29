# Deadline-focused upgrade plan — 2026-10-29

Prepared before implementation. Official deadline: October 30, 2026, 10:00 PDT / 13:00 EDT.
Authority: https://nebiusglobalaihackathon.devpost.com/rules

1. Real Nemotron coding-agent capture (2–3 hours, high benefit, medium risk).
   Capture a real generation, execute it, and preserve that exact source for diagnosis and repair.
   Acceptance: actual inference/usage recorded; hidden tests withheld; unsafe edits rejected;
   healthy generations retained as healthy; original fixtures untouched.
2. Verification correctness and controlled ablation (2 hours, high benefit, medium risk).
   Fail closed on crashed acceptance processes, missing/duplicate checks, absent traces and
   unreproduced baselines. Omit individual edits and measure which fixed failures return.
   Acceptance: adversarial tests for each failure mode; dependent edits marked inconclusive;
   bounded causal claims, not claims about model internals or generalization.
3. Evidence and regression export (1–2 hours, high benefit, low-to-medium risk).
   Export traces, proposals, measured checks, interventions and source/oracle hashes.
   Generate executable pytest replay witnesses from measured fixed checks.
   Acceptance: witness reproduces baseline failure and repaired success; source drift fails;
   unverified repairs cannot export a passing witness. No model-written truth oracle.
4. Comparative evaluation and dashboard (1–2 hours, high benefit, medium risk).
   Re-run the original 26 cases and three scenarios without editing labels or prompts.
   Save separate results, including unsuccessful attempts and execution provenance.
   Acceptance: old reports untouched; complete UI flow inspected; cost/usage visible.
5. Demo and submission documentation (under one hour, high benefit, low risk).
   Check public repository, test build, video, sponsor runtime, license and testing instructions.
   Acceptance: missing external deliverables stay explicitly incomplete.

Audit observations: the original three agents are deterministic fixtures; causal links are
priority heuristics; original replay ignored acceptance exit status and disappearing failed
checks; README references absent ignored submission documents. Baseline: 36 tests pass and
production frontend builds when subprocess/filesystem sandbox restrictions are lifted.

The untracked scripts/rewrite-commit-dates.sh was present before this work. It is unrelated to
the upgrades and was not executed or modified. Historical timestamps are not used as evidence
of eligibility; explain project history truthfully in the submission.
