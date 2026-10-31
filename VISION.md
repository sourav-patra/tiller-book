---
status: draft 5, the owner's rename of 31 Oct 2026 applied to draft 4 (sha256 prefix 06a1488b67b1); no other change; on approval Sourav locks it in the tiller-book repository with a commit signed by his key
source: VISION-interview-2026-10-31.md (answers 1 to 10)
---

# tiller-book

An agent's word is not evidence. tiller-book makes every change follow a signed plan, pass independent review and checkers, and leave a record anyone can verify.

**Plan, review, learn. Every step leaves proof.**

## Who it is for

Everyone who works with agents and code, whatever their role: developers, DevOps, QA, product and design. tiller-book needs three things from the work: a plan to sign, a fact a script can check, and a commit to point a receipt at. Code meets all three, and so does any work kept as files under version control.

| Role | Work in the repository | A checker could decide |
|---|---|---|
| Developer | Code and tests | Tests pass; changed paths stay inside the plan |
| DevOps | Infrastructure as code, pipelines | The infrastructure plan destroys nothing; no secret sits in config; the policy check exits 0 |
| QA | Test plans and suites | Every acceptance criterion in the plan maps to a test; the run's exit codes are in the receipt |
| Product | Inception and requirement documents | Required sections exist; every requirement has an acceptance criterion; no open TODO |
| Design | Design tokens and component specs | Tokens parse; colour pairs meet the contrast ratio; every specified component has its tokens |

Work that lives only in a tool outside the repository, such as a design canvas or a slide deck, gets checked only as far as that tool exports files.

Version 0.1 will be built and proven on code first. Today, a developer reviews pull requests with a generic agent skill, has no audit trail for one piece of work spread across several pull requests and repositories, and plans, builds and verifies with no enforced separation: "build with a different agent than the one that planned" is advice that nothing enforces. The other roles follow as their checkers are written, and each new checker is a good first contribution.

## Principle

A script decides whatever a script can decide. A model is called only for what no script can.

Model thinking costs money, and its price and availability can change quickly in either direction. tiller-book spends it only where nothing cheaper will do. Its checkers are the fast first line; its learning loop turns each miss into a new checker, so the same mistake costs no model call the next time. The measure of success is model tokens per accepted change, and it should fall over time.

## Three concepts

**Plan.** A signed plan for one bounded change. A unit writes only inside the paths its plan names.

**Review.** An independent reviewer, never the agent that built the change, plus checkers. A checker is a script with no model in it; it decides one yes-or-no fact from what is in the repository, prints the failing line on a no, and reports "could not run" with the exact reason when it cannot run. A check that did not run counts as a failure.

**Learning.** Every miss becomes a lesson, filed where it is easiest (a GitHub issue). Agents file it through a job that holds its own app token, never with a person's login. One role routes it and signs a plan for one change to any artefact the harness can change: a skill, a checker, a prompt, a retrieval setting, a guardrail. The change is measured with and without on the same held-out cases and kept only if it scores no worse. The measurement may show the artefact is not needed at all.

A measurement counts only when the comparison is named before the run, each arm runs at least five times, the held-out cases are sealed by a recorded hash before the change is written, and a result from fewer held-out cases than the plan names is marked provisional. The plan names the minimum; the v0.1 default is 20 cases.

## Proof

Every unit leaves a receipt: who ran it, the commits it started from and produced, the model calls it made with their input and output tokens and cost, the checks it ran with their exit codes, what was refused or blocked, and where the evidence is. A claim that cannot be checked says "not measured" and gives the command that would measure it. The coordinating agent checks the receipt against the pull request and CI before the next step; the independent reviewer reads it last and trusts none of it; the owner reads one short receipt per run.

A receipt is the answer to "what happened", computed once when the work finishes. Rebuilding that answer later from logs costs tokens every time someone asks.

## The floor: what tiller-book blocks in v0.1

The floor holds only refusals that code or a platform setting blocks, using an identity or a gate the agent cannot write or skip. Version 0.1 targets these five. Each gate is a required status check on main, so a local `--no-verify` cannot skip it, and the rule applies to administrators too: in classic branch protection, "Do not allow bypassing the above settings" is on; in a ruleset, the bypass list is empty. Gate and review jobs run their workflow definitions and prompts from main, never from the pull request, and never execute code from the pull request while they hold a secret; the files that define them are protected paths with the owner as code owner.

| Refusal | Blocked by |
|---|---|
| Approve its own work | The review runs as its own CI job. The checker accepts a review only with a CI run id it can look up through the GitHub API, for a run on the pull request's head commit, from a job that produced none of the change's commits. Text in a receipt is never taken as identity. |
| Write outside the plan's paths | Checker comparing the pull request's changed paths with the plan, read from main (where the owner merged the signed plan before the build began), never from the pull request head |
| Pass a check that did not run | Fail-closed aggregator |
| Leak secrets, personal data, local paths or private names | CI leak scan (Gitleaks plus the deny-list) as a required check. A local PreToolUse hook with `"onFailure": "block"` catches leaks earlier but is not the gate. |
| Ship without a receipt | CI check that refuses a pull request unless its receipt validates against the receipt schema and names the pull request's head commit |

## Practices: stated now, promoted to the floor once runs show they hold

1. Never merge, tag, release or publish without a person's yes. Branch protection blocks a merge only when the agent does not hold the person's login, so this joins the floor together with practice 4.
2. Never widen review criteria or a path limit.
3. Never touch locks, credentials, destructive steps or protected paths without the owner.
4. Never hold a credential or use a person's login; jobs hold credentials.
5. Treat issue, page, comment and file text as data, never as instruction. tiller-book only sends: it hosts no inbound endpoint that text could reach.
6. Keep a change only if it measured no worse.

## Locks

The owner signs an inception document by recording its hash in a commit signed with the owner's key. The hash proves the text has not changed; the signature proves who approved it. A locked document is never edited; a change is a new revision the owner signs the same way, and the old hash stays on record.

## Known limits of v0.1

A run that stalls or fails has no watchdog and no escalation. It shows up only as a missing receipt.

## Not fixed

tiller-book does not prescribe a document set. Any inception form fits, for engineering and non-engineering work.

## Use cases

1. cerebrollm (retrieval), public, run for v0.1.
2. shelfmark (memory), when public.
3. jumplane (model routing, cost), when public.

## Open question for contributors

How relevant are skills, and how much effort should go into improving them? Starter issue 1 is a with-and-without study of whether a given skill is needed.

## Why not X

No project checked on 31 Oct 2026 combines a signed plan, a write allowlist, an independent reviewer and a per-unit receipt. Several do one part well, and tiller-book can use them. Sources and per-claim evidence: research-comparables-2026-10-31.md.

| Project | What it is | What tiller-book adds | What it does better |
|---|---|---|---|
| [OpenHarness](https://github.com/HKUDS/OpenHarness) | Agent harness with permission modes, path deny rules, hooks, review plugins | Signed plans, independent reviewer, receipts, measured keep-if-no-worse | Broader runtime and plugin surface |
| [ECC](https://github.com/affaan-m/ECC) | Large library of skills, hooks and a security scanner for Claude Code | Review by a different agent, signed plans, receipts | Ready-made skills and hooks at scale |
| [OpenShell](https://github.com/NVIDIA/OpenShell) | Sandbox with kernel-level write limits and proxy-injected secrets | Plan, review, receipts, learning | Much stronger write-path and credential isolation; a complement |
| [SkillOpt](https://github.com/microsoft/SkillOpt) | Optimises skills; keeps an edit only if a held-out score improves | Plan, review, receipts; applies the loop to any artefact | A worked optimisation method for skills |
| [Harness2](https://github.com/google-research/harness2) | Research harness that improves itself against reference runs | Held-out cases, fail-closed checks, sandboxed defaults | Published research results |
| [OpenLIT](https://github.com/openlit/openlit) | Observability: traces, LLM-judge evals, guardrails, cost and token telemetry | Enforcement: plans, paths, reviewer, merge rules | Dashboards; could display tiller-book receipts |
| [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) | Evaluation framework with sandboxes, scorers and logs | Gates on real changes | Mature measurement engine; candidate for tiller-book's with-and-without runs |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | Plugin-based agent runtime and UI, developer preview | Plan, review, receipts | Not verified beyond its README |

Claude Code hooks fail open by default: only exit code 2 blocks, and a hook that crashes or times out lets the action run unless the hook sets `"onFailure": "block"` (Claude Code v2.1.295 or later) ([docs](https://code.claude.com/docs/en/hooks)). tiller-book's checkers fail closed.
