# Babycat Codex Rules

## Scope

- Treat babycat as a connected multi-service project: `app`, `api`, `web`, `config`, `docker`, `tests`, `docs`.
- Do not conclude from one file alone. Check the caller, callee, config, and tests around the change.
- If the user's request is narrow, still check whether the real issue is a higher-level design or boundary problem.

## Before Changing Code

- Briefly state the target responsibility.
- Briefly state the direct dependencies.
- Briefly state the likely impact area across directories.
- Briefly state the needed verification.

## Boundary Rules

- Treat endpoint, schema, env var, config format, proxy, and file naming changes as cross-boundary changes.
- Treat `config/` and `data/` as runtime state, not just source files.
- Assume Jetson, NVIDIA, MediaMTX, and ONVIF paths may fail differently from a normal local dev machine.
- Keep permanent rules in `AGENTS.md`. Put repeatable procedures in skills.

## Working Style

- Prefer explaining responsibility, data flow, failure modes, and validation before implementation details.
- If the request is ambiguous, confirm the target behavior, no-change boundaries, runtime environment, and verification goal before implementing.
- Default to `app` and `api` as the primary refactor targets. Treat `web` mainly as a contract consumer and validation surface.
- When changing one layer, check whether `app`, `api`, `web`, `config`, `tests`, and `docs` need follow-up updates.
- If verification cannot be run in the current environment, say so and name the remaining risk.
- When introducing a new identifier, do not reuse short generic names without checking for collisions in the same local scope first. Treat imports such as `t`, `state`, `status`, `data`, `config`, `open`, and `event` as collision-prone by default.
- After string extraction, i18n work, or composable adoption, re-check event handlers and state mutation paths for identifier shadowing or renamed symbol conflicts before considering the change done.
