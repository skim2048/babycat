---
name: babycat-cross-boundary-check
description: Use when a change may cross app, api, web, config, docker, tests, or docs boundaries, especially for endpoints, schemas, env vars, proxies, config formats, and file naming rules.
---

# babycat-cross-boundary-check

## When to use

- When changing endpoints, request/response schemas, SSE payloads, env vars, config files, docker wiring, or clip naming/storage rules.
- When a change starts in one layer but may break another layer silently.

## Do not use when

- The task is isolated to internal formatting or comments with no runtime effect.
- The task is a purely local implementation detail with no contract or runtime boundary impact.

## Steps

1. Identify the source of truth for the behavior.
2. Check which of `app`, `api`, `web`, `config`, `docker`, `tests`, and `docs` consume or describe it.
3. Mark the producer side and every consumer side.
4. List what must stay compatible and what may need coordinated edits.
5. Call out any boundary that cannot be verified in the current environment.

## Definition of done

- The producer, consumers, compatibility assumptions, and follow-up files are identified.
- No cross-boundary change is treated as single-file work by accident.
