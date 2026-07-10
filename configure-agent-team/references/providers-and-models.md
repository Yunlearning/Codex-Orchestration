# Providers and Models

Use exact model IDs, validate them against the active execution host, and keep provider authentication separate from this skill.

## Model discovery order

1. Inspect the active task's model picker or callable tool schema when it lists host-supported models and efforts.
2. Run `scripts/inspect_models.py` for the installed Codex CLI catalog.
3. Inspect the destination host when work will run remotely.
4. Use official provider model documentation to normalize a user-facing name.
5. If these sources disagree, prefer the host that will execute the task and disclose the mismatch.

Do not treat a missing CLI entry as proof that a newer desktop model is unavailable. Do not treat an official API model ID as proof that the user's Codex provider or account can run it.

## Current examples

Examples verified on July 9, 2026 include:

| Display name | Model ID | Typical role |
| --- | --- | --- |
| GPT-5.6 Sol | `gpt-5.6-sol` | High-capability orchestrator |
| GPT-5.6 Terra | `gpt-5.6-terra` | Balanced orchestrator or executor |
| GPT-5.6 Luna | `gpt-5.6-luna` | Fast, lower-cost executor |
| GPT-5.5 | `gpt-5.5` | Complex orchestration and execution |
| Claude Fable 5 | `claude-fable-5` | Demanding long-horizon orchestration |
| Claude Opus 4.8 | `claude-opus-4-8` | Complex agentic coding and orchestration |
| Claude Sonnet 5 | `claude-sonnet-5` | Scaled executor work |

These are examples, not defaults or an allowlist. Recheck at configuration time.

## Reasoning effort

Normalize “Extra High” to `xhigh`. Use `auto` when the user wants the model default. Validate each effort against that model on the execution host; support differs by model and surface.

Prefer high effort for ambiguous planning, architecture, synthesis, and hard verification. Prefer medium or high for bounded execution unless the task demonstrates that more effort improves results. A cheap model at maximum effort can still be less economical than a stronger model at a calibrated effort, so evaluate the complete workload.

## Project scope

Project scope is the portable default. It can set the orchestrator `model`, reasoning effort, `[agents]` concurrency, and a custom executor model under `.codex/agents/`.

Project config cannot override machine-local provider selection or provider definitions. Therefore:

- Use project scope when both IDs are already available through the active provider.
- Do not write `model_provider` or credentials into project files.
- Tell collaborators which provider access they need without committing secrets.

## Personal and cross-provider scope

Use personal scope only with explicit approval. A personal custom agent can carry supported normal Codex config keys, including a provider ID, but that provider must already be configured and authenticated.

OpenAI credentials do not grant Claude access. Codex custom HTTP providers currently use the Responses protocol; Anthropic's native Messages API is not interchangeable. Claude may be available through a Codex-supported integration such as an already-configured provider or Amazon Bedrock. Discover the provider's actual catalog and use its model ID format instead of assuming the Claude API ID.

Never generate provider definitions from guesses. Never request that a user paste an API key into chat or a committed TOML file. Use an environment variable or the provider's supported authentication flow.

## Runtime role limitation

Current local Codex releases can load named custom agents with distinct model settings. Some hosted or embedded spawn primitives may not expose a named-role selector. In those surfaces, the parent cannot prove that a requested executor model was used.

When named-role selection is unavailable:

1. Disclose the limitation.
2. Use the runtime's inherited/default worker only with user consent.
3. Do not report executor-model cost or usage claims as measured facts.
4. Suggest starting a compatible local Codex task if exact role pinning is required.

## Sources

- [OpenAI Codex subagents and custom agents](https://developers.openai.com/codex/subagents)
- [OpenAI Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [OpenAI model catalog](https://developers.openai.com/api/docs/models)
- [Anthropic model overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Anthropic model IDs and versioning](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions)
- [Anthropic orchestrator-workers pattern](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic production multi-agent lessons](https://www.anthropic.com/engineering/multi-agent-research-system)
