---
name: configure-agent-team
description: Interactively choose, validate, and configure an orchestrator model plus an executor model for Codex custom-agent and parallel-subagent workflows, then coordinate bounded workers through a reliable plan-delegate-synthesize-verify protocol. Use when a user asks to set up orchestrator/worker models, assign different models to the main agent and subagents, stretch usage with cheaper executors, configure custom Codex agents, run 2-5 subagents, or improve multi-agent delegation and synthesis.
---

# Configure Agent Team

Configure the main Codex session as the orchestrator and a custom Codex agent as the executor. Keep model discovery dynamic, preserve existing configuration, and never promise a fixed cost or usage-limit multiplier.

## Gather the setup

Inspect the current workspace, Codex version, available model catalog, and subagent tool schema before asking questions. Run:

```bash
python3 <skill-dir>/scripts/inspect_models.py
```

Treat the CLI catalog as one capability signal, not the only one. A desktop host or remote destination may expose newer models than the local CLI catalog. Accept a model when the active host explicitly exposes its exact ID and supported reasoning effort.

Ask only for missing values in one compact prompt. Use this reply shape:

```text
orchestrator=<model-id>@<effort>, executor=<model-id>@<effort>, workers=<1-5>, scope=<project|personal>, run_now=<yes|no>
```

Explain that `xhigh` means Extra High. Allow `auto` to use the model's default effort. Default `workers` to `3`, `scope` to `project`, and `run_now` to `no` when the request only asks for configuration. Do not choose either model for the user when they asked to choose models. If `run_now=yes`, require the concrete task objective too.

Ask for a provider ID only when the selected model is not available through the active provider. Read [providers-and-models.md](references/providers-and-models.md) before configuring Claude, a custom provider, or different providers for the two roles.

## Normalize and confirm

Map display names to exact model IDs only from a current runtime catalog, an active tool schema, or official provider documentation. Never invent a slug.

Echo this summary before writing:

```text
Orchestrator: <provider>/<model> at <effort>
Executor: <provider>/<model> at <effort>
Parallel executors: <count>
Scope: <scope>
```

If a model is absent from the CLI catalog but is explicitly available on the active host, note the catalog mismatch and pass `--confirm-unlisted-models`. Otherwise, stop and ask for a supported ID or provider setup. Do not use that flag merely to bypass uncertainty.

Do not claim “5x limits,” “3x cheaper,” or another fixed multiplier as a guaranteed outcome. Describe the setup as a way to trade orchestrator quality, executor cost, throughput, and total token usage. Multi-agent runs may consume more total tokens.

## Choose the scope

Use `project` by default. It writes:

- `.codex/config.toml` for the orchestrator model and concurrency settings.
- `.codex/agents/orchestrated_executor.toml` for the executor model and behavior.

Use `personal` only after the user explicitly approves changing their global Codex defaults. It writes equivalent files under `${CODEX_HOME:-$HOME/.codex}`.

Do not pass provider flags in project scope. Codex treats provider selection and credentials as machine-local configuration. Use personal scope only when the user explicitly wants a preconfigured provider selected globally or different providers assigned to the two roles.

## Configure safely

Resolve `<skill-dir>` to this skill's directory. Always preview first:

```bash
python3 <skill-dir>/scripts/configure_agent_team.py \
  --scope project \
  --root <workspace> \
  --orchestrator-model <model-id> \
  --orchestrator-effort <effort-or-auto> \
  --executor-model <model-id> \
  --executor-effort <effort-or-auto> \
  --workers <count>
```

Review the diff. Then rerun the same command with `--apply`. Add `--confirm-unlisted-models` only under the validation rule above. For personal scope, add the approved provider IDs with `--orchestrator-provider` and `--executor-provider` as needed.

Never place API keys or bearer tokens in generated files. Require providers and authentication to be configured separately. Refuse to overwrite an unmanaged agent file unless the user explicitly authorizes `--force-agent-file` after reviewing it.

Validate the resulting TOML. Report that model changes apply to a new Codex task or session; do not claim the already-running root model switched in place.

If `run_now=yes`, launch work only when the current task already has the selected orchestrator and named executor role loaded. Otherwise, do not run the task under stale roles; provide a ready-to-use next-task prompt that invokes this skill and includes the objective.

## Run the team

Read [orchestration-protocol.md](references/orchestration-protocol.md) before delegating work.

Use a single agent for simple work, tightly coupled edits, or tasks where coordination costs exceed the likely gain. Use parallel executors for independent, bounded work such as exploration, research lanes, tests, triage, reviews, or disjoint implementation slices.

Treat the configured worker count as a maximum, not a requirement. A user's `run_now=yes` permits suitable delegation but does not require wasteful fan-out; state when the fit gate selects zero workers.

Prefer `2` workers for moderate tasks and `3-5` for genuinely broad tasks. Never exceed the user's count or the runtime's concurrency cap. Keep `agents.max_depth = 1` unless the user explicitly requests recursive delegation.

When the runtime exposes named custom-agent roles, spawn `orchestrated_executor`. When its spawn primitive does not expose a role or model selector, say that executor pinning cannot be guaranteed in that surface and use the runtime's inherited/default worker behavior. Never silently claim the configured executor model was used.

Give every executor a complete bounded contract: objective, relevant context, exclusive file or investigation scope, constraints, expected output, verification, and stop conditions. Dispatch independent work together. Keep overlapping writes serialized.

Before dispatch, write a detailed, inspectable execution plan covering the target end state, dependencies, worker ownership, integration order, verification, and stop conditions. Do not expose private chain-of-thought.

Remain responsible for user intent, the dependency graph, conflict resolution, synthesis, end-state verification, and the final answer. Treat worker output as evidence, not authority.

## Handle failures

Retry a failed worker at most once after correcting a specific issue such as missing context, invalid scope, or a transient tool error. Do not repeat identical failing prompts or expand fan-out to compensate for a bad decomposition.

Interrupt or redirect workers that drift outside scope, duplicate another worker, or threaten overlapping writes. If a worker returns partial results, inspect any shared artifacts before deciding whether to finish locally, reassign the missing slice, or report a blocker.

## Resources

- `scripts/inspect_models.py`: print a compact current Codex model catalog.
- `scripts/configure_agent_team.py`: preview and apply safe project or personal configuration changes.
- [orchestration-protocol.md](references/orchestration-protocol.md): role boundaries, effort scaling, task contracts, synthesis, and verification.
- [providers-and-models.md](references/providers-and-models.md): provider portability, model-ID validation, Claude caveats, and source links.
