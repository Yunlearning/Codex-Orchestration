---
name: codex-orchestration
description: Use the current Codex session model as the root orchestrator, route eligible delegated work to a required executor model, and optionally obtain a read-only plan review from an advisor model. Explicitly invoke from the Desktop slash list as /codex-orchestration, or select Codex Orchestration through /skills in CLI and IDE. Preserves native Plans, Goals, delegation decisions, worker counts, integration, and verification.
---

# Codex Orchestration

Treat the model already selected for the current Codex task as the only orchestrator. Add model routing around it; do not replace Codex's orchestration.

## Parse the invocation

Accept natural inline choices such as:

```text
/codex-orchestration executor: GPT-5.6 Luna extra high, advisor: Anthropic Fable 5 extra high
/codex-orchestration executor: GPT-5.6 Luna extra high, advisor: none
```

In CLI or IDE surfaces, prefer selection through `/skills`. A plugin-installed skill may appear under its qualified runtime name `$codex-orchestration:codex-orchestration`; a standalone copy appears as `$codex-orchestration`.

The executor is required. The advisor is optional, but the user must choose a model or explicitly choose `none`. Ask once for only the missing values:

```text
executor=<model>@<effort-or-auto>, advisor=<model>@<effort-or-auto>|none
```

If an old invocation contains `orchestrator:`, explain that the active session model already owns that role. Do not switch or persist a second orchestrator. If the host exposes the active model name, report it; otherwise call it `current session model` without guessing.

Normalize “Extra High” to `xhigh`. Resolve display names to exact IDs only from the active host, its model picker, the local catalog, or official provider documentation. Ask for an exact ID when the mapping is ambiguous; never invent one.

Do not ask whether to use subagents, how many to use, whether to create a Plan or Goal, or whether to run now. Those remain native Codex decisions.

Read [providers-and-models.md](references/providers-and-models.md) when a model is unavailable in the active catalog, the seats use different providers, or the user requests persistence.

## Preserve native Codex

The current root model retains user intent, planning, architecture, delegation, integration, review, and final verification. Let it decide normally whether to plan, use a Goal, work directly, delegate, choose roles and worker count, steer children, integrate results, and verify completion.

Never create a second orchestrator, Goal loop, fixed worker-count rule, automatic spawn rule, or replacement verification protocol. Never set `agents.max_threads` or `agents.max_depth`, redefine built-in roles, or change sandboxing, approvals, tools, hooks, authentication, or provider credentials.

Model selection does not authorize a spawn. An advisor setting does not force a plan for trivial work, and an executor setting does not force delegation.

## Inspect native routing

Inspect the `spawn_agent` schema exposed in this task. Trust the callable schema over version assumptions.

- A live model route requires native `model` and `reasoning_effort` fields.
- A loaded persistent route requires visible native `agent_type` selection.
- A selected non-root model needs a self-contained fresh or partial fork. A full-history fork inherits the root model.
- If required controls are hidden, report the requested seat as unavailable on this surface. Never imply that a model ran when Codex did not accept the route.

## Use the optional advisor

Use the advisor only when it is configured and the root has independently produced a non-trivial plan or proposed executor task list worth reviewing. The advisor is a bounded, read-only second opinion—not a co-orchestrator or a supervisor.

Before releasing work to executors:

1. The root writes the plan and proposed executor slices using its normal Plan or Goal behavior when useful.
2. Give one advisor all relevant context in a self-contained review packet: user intent, requirements, constraints, material repository evidence, the root plan, proposed executor slices, dependencies, acceptance criteria, and verification checks.
3. Route that child to the selected advisor model and effort on a fresh or smallest-sufficient partial fork. Use a native general-purpose role when exposed; do not redefine a built-in role.
4. Require the advisor's first nonblank output line to be exactly one of:

```text
PLAN_APPROVED
PLAN_REVISE
ADVISOR_BLOCKED
```

Use this contract in the advisor handoff:

```text
Act as a read-only second-opinion advisor to the root Codex orchestrator.
Review the supplied plan and executor task list for requirement coverage,
incorrect assumptions, missing dependencies, shallow or overlapping task
boundaries, unsafe parallelism, integration risk, and weak acceptance or
verification criteria. Do not edit, run mutating tools, spawn, contact
executors, rewrite the whole plan, or decide on the root's behalf. Return only
to the root. Start with PLAN_APPROVED, PLAN_REVISE, or ADVISOR_BLOCKED.
```

`PLAN_APPROVED` means no material gap was found. `PLAN_REVISE` must be followed by a concise, prioritized list of material omissions, shallow or conflicting executor slices, missed dependencies, risks, or missing acceptance and verification checks. Style preferences alone do not justify revision. `ADVISOR_BLOCKED` must name the missing context, unavailable capability, or transport failure and the minimum action needed. Silence, malformed output, and ambiguous prose are never approval.

The advisor must not edit files, change the plan directly, spawn children, assign work, message executors, or accept their work. It reports only to the root. The root adjudicates every suggestion, revises its own plan, and may request one confirmation review after material changes. Retry a transport failure or malformed response at most once. After two valid reviews, stop the loop: if material disagreement remains, disclose it and ask whether to revise further or explicitly proceed without advisor approval. Never falsely report `PLAN_APPROVED`.

Only the root releases work to native delegation after `PLAN_APPROVED` or an explicit root disposition of the remaining advice. An unavailable requested advisor is not silently replaced by the root model or skipped; report the limitation and ask the user to choose `advisor: none` or use a compatible surface/new task.

## Use the executor

Keep the selected executor as a task-local preference. After Codex independently decides a bounded execution subagent is worthwhile:

1. Use Codex's built-in `worker` role when that selector is exposed and appropriate. Do not redefine it.
2. For a self-contained execution slice, give the native worker the objective, constraints, relevant context, owned files, acceptance criteria, and verification command. Use a fresh fork and pass the executor model and effort when those fields are exposed.
3. If the worker needs recent task context, use the smallest sufficient partial fork. If it needs full history, let it inherit the root model instead of forcing the executor.
4. Prefer the executor only for well-scoped implementation or other instruction-following work. Keep ambiguous planning, cross-cutting synthesis, integration, and final review with the root unless Codex independently judges otherwise.
5. Let the executor return through Codex's existing subagent channel. The root inspects the result and evidence before accepting it.

For MultiAgentV2, a full-history fork inherits the root model and rejects role/model overrides. The fresh or partial fork above is a native transport requirement applied only after delegation is already justified; it must never become a reason to spawn. Do not discard needed context merely to force a cheaper model.

If live model controls are hidden, use an already loaded custom `executor` role only when `agent_type` is visible and Codex accepts it on a non-full fork. Otherwise keep the work with the root or report that exact executor routing is unavailable. Never claim the executor ran merely because it was requested.

## Report activation

Return a compact status before continuing the user's work:

```text
Codex Orchestration
Orchestrator: <active model name if exposed, otherwise current session model> — active
Advisor: <provider/model>@<effort> — <live route|loaded role|unavailable>, or none
Executor: <provider/model>@<effort> — <live route|loaded role|unavailable>
Native Plan/Goal/delegation behavior: unchanged
```

Then continue normally. The user may start or continue a Goal in that same task. Do not create or modify Goal state solely because this skill was invoked.

## Persist only when requested

Task-local activation is the default. If the user explicitly requests future-task role defaults, ask for `scope=<project|personal>` and preview the bundled configurator:

```bash
python3 <skill-dir>/scripts/configure_orchestration.py \
  --scope project \
  --root <workspace> \
  --executor-model <model-id> \
  --executor-effort <effort-or-auto> \
  --advisor-model <model-id> \
  --advisor-effort <effort-or-auto>
```

Omit the advisor flags when it is disabled. Use `--remove-advisor` to delete a previously managed advisor role. Review the diff, then repeat with `--apply`. Require explicit approval for personal scope. Add `--confirm-unlisted-models` only after another active-host source confirms every exact model and effort.

Persistent mode leaves the root startup model untouched and adds model-only `[agents.executor]` and optional `[agents.advisor]` layers. It must not shadow `default`, `worker`, or `explorer`, and the layers must contain no orchestration instructions. Configuration loads only in a new task; an existing task-scoped Goal does not move there. Custom roles still require visible native role selection and a non-full fork.

For output from an older release, use `--migrate-legacy` only after reviewing the deletion preview. Back up and remove only proven managed legacy files. Leave legacy root model and concurrency settings for manual review because user intent cannot be reconstructed safely.

## Protect the savings claim

The goal is to preserve the frontier orchestrator's included allowance during executor-heavy work. The optional advisor trades a small, high-value review pass for quality and may consume a different provider's allowance. Do not promise 65% fewer raw tokens, a fixed monetary saving, or more agents. Multi-agent work can increase total tokens, so never delegate or invoke an advisor solely to chase a savings number.

## Resources

- `scripts/inspect_models.py`: inspect the installed Codex CLI catalog.
- `scripts/configure_orchestration.py`: preview and apply optional persistent role settings.
- [providers-and-models.md](references/providers-and-models.md): provider, routing, fork, Goal, and usage-limit constraints.
