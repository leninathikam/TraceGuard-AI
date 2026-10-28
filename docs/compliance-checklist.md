# Competition compliance checklist

Source: https://nebiusglobalaihackathon.devpost.com/ and /rules, read 2026-10-25.
Deadline: **Friday, October 30, 2026, 10:00 AM Pacific.** Judging runs Dec 1–15, 2026.

| Requirement (from the rules) | Status | Evidence / action |
| --- | --- | --- |
| Runs on Nebius Token Factory or AI Cloud: "makes a runtime call to the Token Factory inference API" | Verified live 2026-10-25 | `nebius.py` calls `api.tokenfactory.nebius.com/v1/chat/completions`; `scripts/check_nebius.py` and the benchmark ran against it (≈110 Nemotron calls). |
| Uses at least one NVIDIA open-source model | Built | Default `nvidia/nemotron-3-super-120b-a12b`; model ID logged on every diagnosis. |
| Fits a track (Coding and Agentic Engineering: "agents that write, run, and test code in Token Factory") | Yes | Nemotron writes the repair (config or Python), TraceGuard runs it and tests it (Scenario C runs visible + held-out unit tests). |
| Stage One pass/fail: genuine attempt at the track, applies the required APIs | Yes, once the live call is verified | — |
| Working demo URL (hosted app or test build) | **TODO** | Deploy the Docker image (see `docs/devpost-submission.md`) and keep it up until Dec 15. Provide any credentials in testing instructions. |
| Demo video < 3 min, public on YouTube, no copyrighted music | **TODO** | Script in `docs/demo-script.md`. Must show Token Factory + Nemotron in use. |
| Public GitHub/GitLab/Bitbucket repo | **TODO** | Push this repo; make it public. |
| Open-source license visible in the repo About section | Ready | `LICENSE` (MIT) at the root; GitHub detects it automatically. |
| README with setup instructions, how Nemotron / Token Factory are used | Done | `README.md`. |
| Feedback on Token Factory / AI Cloud / NVIDIA tools | **TODO (must be your own experience)** | Write after the live runs. Eligible for the "Most Valuable Feedback" prize. |
| New project, or explain significant updates if it existed before Aug 26 | New | Built during the Submission Period. |
| Third-party integrations authorised | Yes | No third-party APIs besides Nebius. Dependencies: FastAPI, Pydantic, httpx, React, Vite (MIT/BSD). |
| English materials | Yes | — |
| Project available free for judging until judging ends | **TODO** | Keep the hosted demo and credits alive through Dec 15, 2026. |

Judging criteria (equal weight): Technological Implementation, Design, Potential Impact, Quality of the Idea.
Tie-break order follows that list, so Technological Implementation matters most in a tie.

Optional: the Builder Program offers Token Factory credits; "Best Use of Tavily" is a separate bonus prize (not used here).
