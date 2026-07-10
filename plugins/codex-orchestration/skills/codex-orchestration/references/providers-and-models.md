# Providers, Models, and Native Routing Limits

Use exact model IDs, validate them against the host that will execute the task, and keep authentication separate from this skill.

## Discovery order

1. Treat the model already selected for the active task as the root orchestrator.
2. Inspect the active task's model picker and `spawn_agent` schema for executor and advisor routing.
3. Run `scripts/inspect_models.py` for the installed Codex CLI catalog.
4. Inspect the destination host when work will execute remotely.
5. Use official provider documentation to normalize a display name.
6. If sources disagree, prefer the executing host and disclose the mismatch.

A missing CLI entry does not prove that a newer Desktop model is unavailable. An API model ID does not prove that the user's Codex account or configured provider can run it.

Do not keep a static model-name table in this skill. Catalogs, aliases, efforts, and availability change.

## Role selection

The current task model is always the orchestrator. Never ask the user to choose another orchestrator or modify the current task's root model. If its identity is not exposed, report `current session model` rather than guessing.

OpenAI's current Codex guidance describes GPT-5.6 Sol as the quality and reasoning-depth choice, Terra as the balanced default, and Luna as the speed and affordability choice for lighter or high-volume work. This makes a current Sol task with Luna executors a sensible example, not a universal default. Recheck availability and exact IDs on the active host.

Use the executor for bounded work whose objective, constraints, context, and acceptance checks are already clear. A lower-cost model is not suitable merely because a subagent exists.

The optional advisor is a read-only critic for a non-trivial root plan and proposed executor slices. A model from a different family or provider can offer a useful second lens, but only if that provider is already configured and Codex can route to it. The advisor reports only to the root; it never coordinates with executors.

## Reasoning effort

Normalize “Extra High” to `xhigh`. Use `auto` when the user wants a model's default. Validate the effort independently for executor and advisor; supported levels differ by model and surface.

For a persistent role layer, resolve `auto` to that role's catalog default when possible. Otherwise a root `model_reasoning_effort` override could accidentally flow into the child model.

## Native live routing

The thinnest path is a native per-spawn override:

```text
spawn_agent(..., model=<child-id>, reasoning_effort=<effort>)
```

Use it only when those fields exist in the active tool schema. Their absence is a capability boundary, not a prompt-engineering problem.

MultiAgentV2 full-history forks inherit the parent role, model, and effort. When the full-history mode is used, Codex rejects role/model overrides and skips role-layer application. Give a selected child a self-contained fresh or smallest-sufficient partial context. Do not discard context required for correctness merely to force a different model.

For an advisor, package all relevant requirements, evidence, the root plan, proposed executor slices, dependencies, acceptance criteria, and verification checks into that self-contained handoff. “All relevant context” does not require copying unrelated chat history.

## Optional persistent roles

Persistent mode can add two user roles without changing the root model:

```toml
[agents.executor]
description = "Optional model-only route for delegated work after Codex independently decides a compatible worker is useful."
config_file = "agents/executor-model.toml"

[agents.advisor]
description = "Optional read-only second opinion for a non-trivial root plan. Reports only to the root and never coordinates executors."
config_file = "agents/advisor-model.toml"
```

Each referenced file is a normal Codex configuration layer containing only the selected model settings:

```toml
model = "<role-model-id>"
model_reasoning_effort = "<effort>"
```

Personal-scope cross-provider layers may additionally contain an already configured `model_provider`. The skill never creates providers or credentials.

These custom roles leave the built-in `default`, `worker`, and `explorer` definitions untouched. User-defined roles take precedence over built-ins with the same name, which is why this project must not redefine them.

A custom role is usable only when the spawn surface exposes `agent_type` and the fork is not full-history. A role file does not make a hidden selector appear.

## Project scope

Project scope is the portable persistence default. It declares only the custom `executor` and optional `advisor` roles under `.codex/`; it does not set the root startup model.

Do not place a provider selection, provider definition, or credential in project files. Project configuration loads only for trusted projects, following Codex's native trust boundary.

## Personal and cross-provider scope

Use personal scope only after explicit approval. It changes future task role defaults under `${CODEX_HOME:-$HOME/.codex}`.

Direct per-spawn overrides do not expose a separate provider field, so live routing is limited to models available through the active provider. Cross-provider execution requires a persistent role layer with a supported `model_provider`, an already configured and authenticated provider, visible role selection, and a non-full-history fork.

OpenAI credentials do not grant Anthropic access. Codex custom HTTP providers use the protocol supported by Codex; do not assume that an Anthropic Messages API endpoint is interchangeable. Anthropic models may instead be available through an existing compatible integration such as Amazon Bedrock. Inspect the real provider catalog before choosing an ID.

Never request that a user paste an API key into chat or a committed TOML file. Never generate provider definitions from guesses.

## Current task, persistence, and Goals

The root model is whichever model the user selected when starting or configuring the current task. The skill does not switch it.

Persistent role configuration is loaded when a new task starts; it does not hot-reload. A Goal may run normally in a task where live routing is active. Starting a new task for persistent settings does not transfer an existing task-scoped Goal.

## Usage-limit language

Keep these concepts separate:

- **Raw tokens:** input, cached, and output tokens actually processed. Subagents and advisor reviews can increase this total.
- **Frontier-seat included allowance:** plan usage governed by shared five-hour windows and any applicable weekly limits. Moving eligible execution to another model can preserve the root seat's allowance.
- **Other-provider allowance:** an advisor from another provider consumes that provider's separate allowance or billing; do not combine the two into a universal percentage.
- **Credits:** metered usage after included limits or under flexible pricing.
- **API cost:** separate usage-based pricing when Codex authenticates with an API key.

OpenAI currently lists substantially more local messages per five-hour window for GPT-5.6 Luna than Sol. This supports an illustrative frontier-seat allowance-saving estimate for an executor-heavy mix, not a guarantee about raw tokens, dollars, or all providers. Never force agents or advisor calls to reach a marketing target.

## Truthful status

Report one of these routing outcomes per non-root seat:

- `live route`: the active schema exposes the needed model controls; still confirm actual acceptance when spawning.
- `loaded role`: an already loaded custom role can be selected on a compatible fork.
- `partial`: a full-history child inherited the root model.
- `unavailable`: native role/model controls are hidden or the requested provider is inaccessible.
- `none`: the optional advisor was explicitly disabled.

Never infer the child model from the requested configuration alone. Never substitute the root model for a requested advisor and call the review independent.

## Sources

- [OpenAI Codex subagents and custom agents](https://developers.openai.com/codex/subagents)
- [OpenAI Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [OpenAI Codex role-layer source](https://github.com/openai/codex/blob/main/codex-rs/core/src/agent/role.rs)
- [OpenAI Codex MultiAgentV2 spawn source](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)
- [OpenAI Codex spawn tool schema source](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_spec.rs)
- [OpenAI Codex Goals example](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)
- [OpenAI Codex pricing and usage limits](https://developers.openai.com/codex/pricing)
- [Anthropic orchestrator-workers pattern](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic production multi-agent lessons](https://www.anthropic.com/engineering/multi-agent-research-system)
