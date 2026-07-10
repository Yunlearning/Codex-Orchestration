# Providers, Models, and Native Routing Limits

Use exact model IDs, validate them against the host that will execute the task, and keep authentication separate from this skill.

## Discovery order

1. Inspect the active task's model picker and `spawn_agent` schema.
2. Run `scripts/inspect_models.py` for the installed Codex CLI catalog.
3. Inspect the destination host when work will execute remotely.
4. Use official provider documentation to normalize a display name.
5. If sources disagree, prefer the executing host and disclose the mismatch.

A missing CLI entry does not prove that a newer Desktop model is unavailable. An API model ID does not prove that the user's Codex account or configured provider can run it.

Do not keep a static model-name table in this skill. Catalogs, aliases, efforts, and availability change.

## Reasoning effort

Normalize “Extra High” to `xhigh`. Use `auto` when the user wants a model's default. Validate the effort for each selected model; supported levels differ by model and surface.

For a persistent executor layer, resolve `auto` to the executor model's catalog default when possible. Otherwise a root `model_reasoning_effort` override could accidentally flow into the executor model.

## Native live routing

The thinnest path is the native per-spawn override:

```text
spawn_agent(..., model=<executor-id>, reasoning_effort=<effort>)
```

Use it only when those fields exist in the active tool schema. Their absence is a capability boundary, not a prompt-engineering problem.

MultiAgentV2 full-history forks inherit the parent role, model, and effort. When `fork_turns="all"`, Codex rejects role/model overrides and skips role-layer application. Do not silently change context propagation merely to claim that routing worked.

## Optional persistent role

Persistent mode adds a separate user role:

```toml
[agents.executor]
description = "Optional model-only route for delegated work after Codex has independently decided a compatible subagent is useful. Selecting this role does not authorize delegation."
config_file = "agents/executor-model.toml"
```

The referenced file is a normal Codex configuration layer containing only:

```toml
model = "<executor-model-id>"
model_reasoning_effort = "<effort>"
```

This leaves the built-in `default`, `worker`, and `explorer` definitions untouched. User-defined roles take precedence over built-ins with the same name, which is why this project must not redefine them.

The custom role is usable only when the spawn surface exposes `agent_type` and the fork is not full-history. A role file does not make a hidden selector appear.

## Project scope

Project scope is the portable persistence default. It may set the root `model` and reasoning effort and declare the custom `executor` role under `.codex/`.

Do not place a provider selection, provider definition, or credential in project files. Project configuration loads only for trusted projects, following Codex's native trust boundary.

## Personal and cross-provider scope

Use personal scope only after explicit approval. It changes future task defaults under `${CODEX_HOME:-$HOME/.codex}`.

Direct per-spawn overrides do not expose a separate provider field, so live routing is limited to models available through the active provider. Cross-provider execution requires a persistent role layer with a supported `model_provider`, an already configured and authenticated provider, visible role selection, and a non-full-history fork.

OpenAI credentials do not grant Claude access. Codex custom HTTP providers use the protocol supported by Codex; do not assume that an Anthropic Messages API endpoint is interchangeable. Claude may instead be available through an existing compatible integration such as Amazon Bedrock. Inspect the real provider catalog before choosing an ID.

Never request that a user paste an API key into chat or a committed TOML file. Never generate provider definitions from guesses.

## Current task, persistence, and Goals

The root model can be selected in the current task through Codex's native picker or `/model` where supported. The skill itself cannot silently change the root model.

Persistent configuration is loaded when a new task starts; it does not hot-reload. A Goal may run normally in a task where live routing is active. Starting a new task for persistent settings does not transfer an existing task-scoped Goal.

## Truthful status

Report one of these outcomes:

- `active`: a native live override or an already loaded custom role was accepted for compatible spawns.
- `persistent-only`: the custom role was written but still needs a future compatible task.
- `partial`: a full-history child inherited the root model.
- `unavailable`: native role/model controls are hidden.

Never infer the child model from the requested configuration alone.

## Sources

- [OpenAI Codex subagents and custom agents](https://developers.openai.com/codex/subagents)
- [OpenAI Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [OpenAI Codex role-layer source](https://github.com/openai/codex/blob/main/codex-rs/core/src/agent/role.rs)
- [OpenAI Codex MultiAgentV2 spawn source](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)
- [OpenAI Codex spawn tool schema source](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_spec.rs)
- [OpenAI Codex Goals example](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)
- [Anthropic orchestrator-workers pattern](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic production multi-agent lessons](https://www.anthropic.com/engineering/multi-agent-research-system)
