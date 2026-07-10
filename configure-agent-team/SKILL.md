---
name: configure-agent-team
description: Choose an orchestrator model and an executor model for Codex using only native model and subagent controls. Use when a user wants a stronger root model plus faster or cheaper subagents without replacing Codex planning, Goals, delegation decisions, concurrency, role guidance, or verification behavior.
---

# Configure Agent Team

Configure model seats only. Codex remains the orchestrator.

## Preserve native Codex

Treat these rules as non-negotiable:

- Let Codex decide whether to plan, start or continue a Goal, work directly, spawn subagents, choose their number and roles, steer them, integrate their work, and verify the result.
- Apply the executor preference only after Codex has independently decided to delegate.
- Do not create another planner, supervisor loop, Goal loop, delegation gate, retry policy, worker protocol, or verification protocol.
- Do not set `agents.max_threads` or `agents.max_depth`.
- Do not redefine Codex's built-in `default`, `worker`, or `explorer` roles.
- Do not change sandboxing, approvals, tools, hooks, or provider authentication.

This skill must never spawn a subagent merely to test the configuration.

## Inspect capabilities first

Inspect the current `spawn_agent` tool schema and use the schema actually exposed in this task. Do not infer capabilities from a version number.

Classify the task:

- **Live model override available:** `spawn_agent` exposes `model` and, when needed, `reasoning_effort`.
- **Named role available:** `spawn_agent` exposes `agent_type`.
- **Routing unavailable:** those fields are hidden.

For MultiAgentV2, a full-history fork (`fork_turns="all"`) inherits the root model and rejects role/model overrides. Model routing can apply only when Codex's independently chosen context strategy is compatible with a non-full fork. Do not force a different fork strategy just to make the requested executor model appear to work.

Run the local catalog helper:

```bash
python3 <skill-dir>/scripts/inspect_models.py
```

Treat that catalog as one capability signal. The active desktop host or remote destination may expose a different catalog. Use an exact model ID only when the execution host, its model picker, or official provider documentation confirms it. Never invent a slug.

Read [providers-and-models.md](references/providers-and-models.md) before using Claude, a custom provider, different providers for the two seats, or persistent configuration.

## Ask for the two seats

Ask only for missing model choices in one compact prompt:

```text
orchestrator=<model-id>@<effort-or-auto>, executor=<model-id>@<effort-or-auto>
```

Explain that `xhigh` means Extra High and `auto` uses the model default. Do not ask how many subagents to run or whether to run them. Do not promise “5x limits,” “3x cheaper,” or any fixed multiplier; cost and throughput depend on the task, provider, effort, and number of spawned agents.

Echo the exact IDs, efforts, providers, and capability result before activation.

## Activate the current task by default

Use Codex's native model picker or `/model` command to select the orchestrator model for the root task. A skill cannot silently switch the already-running root model. If a user action is required, tell them exactly what to select and pause until they confirm it.

Keep the executor choice as a task-local routing preference. Continue the user's normal work or Goal without creating a separate workflow.

When Codex independently decides a subagent is useful:

1. Preserve Codex's native role choice and context/fork decision.
2. If the native spawn call exposes model overrides and the chosen fork is not full-history, set the selected executor `model` and `reasoning_effort` on that call.
3. If the call is full-history, omit the overrides; the child inherits the orchestrator model.
4. If model controls are hidden, do not claim live task-local routing. Unless the task already loaded a visible `executor` role and Codex accepted it on a non-full fork, state that the child inherits the root model.

Direct per-spawn model overrides use the active provider. Do not claim cross-provider routing through a field the native tool does not expose.

A user may start a Goal in the same task after the root model is selected. This skill does not create, alter, pause, resume, or replace Goal state.

## Persist only when requested

If the user explicitly wants startup defaults for future tasks, ask for `scope=<project|personal>`. Default to project scope. Require explicit approval for personal scope because it changes global Codex defaults.

Preview first:

```bash
python3 <skill-dir>/scripts/configure_agent_team.py \
  --scope project \
  --root <workspace> \
  --orchestrator-model <model-id> \
  --orchestrator-effort <effort-or-auto> \
  --executor-model <model-id> \
  --executor-effort <effort-or-auto>
```

Review the diff, then rerun the same command with `--apply`. Add `--confirm-unlisted-models` only when another active-host capability source has already confirmed the exact model and effort.

The optional persistent mode writes:

- `.codex/config.toml`: the root startup model plus a separate `[agents.executor]` declaration.
- `.codex/agents/executor-model.toml`: the executor model, effort, and optional provider only.

The `executor` role is additive. It does not shadow `default`, `worker`, or `explorer`, and its layer contains no `developer_instructions` or orchestration policy. It is usable only in a new task whose native spawn surface exposes `agent_type` and selects a non-full-history fork. Never describe it as universal routing.

Persistent configuration does not hot-reload into the current task. Starting a new task does not carry an existing task-scoped Goal into that task.

If the script detects this project's older managed `orchestrated_executor.toml`, use `--migrate-legacy` only after reviewing the removal diff. The migration backs up and removes that managed file. It deliberately leaves `agents.max_threads` and `agents.max_depth` untouched because their prior values cannot be reconstructed safely; flag those keys for manual review.

## Report truthfully

Distinguish these outcomes:

- `active`: the root model is selected and either a native per-spawn override or an already loaded `executor` role was accepted for compatible spawns.
- `persistent-only`: the custom role was written but still needs a future compatible task before it can be used.
- `partial`: a full-history child inherited the root model.
- `unavailable`: the surface hides native model/role selection.

Never report executor cost, usage, or model identity as a fact unless the runtime exposed and accepted the override.

## Resources

- `scripts/inspect_models.py`: inspect the installed Codex CLI catalog.
- `scripts/configure_agent_team.py`: preview and apply optional persistent settings.
- [providers-and-models.md](references/providers-and-models.md): native capability, provider, fork, Goal, and portability constraints.
