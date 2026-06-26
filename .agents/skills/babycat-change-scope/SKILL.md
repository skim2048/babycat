---
name: babycat-change-scope
description: Use before code changes, refactors, bug fixes, or feature work to define the target responsibility, dependencies, impact area, and verification plan in babycat.
---

# babycat-change-scope

## When to use

- Before changing code in `app`, `api`, `web`, `config`, `docker`, `tests`, or `docs`.
- When a user asks for a fix, refactor, feature, or behavior change.
- When the visible issue may hide a larger design or boundary problem.

## Do not use when

- The task is only to summarize, review, or explain existing code without proposing changes.
- The task is only to write or update documentation after the change scope is already known.

## Steps

1. Name the file or module the user pointed to.
2. State that module's actual responsibility.
3. List the direct dependencies that can change behavior.
4. List the surrounding directories or services that may be affected.
5. State the failure modes worth checking.
6. State the smallest useful verification plan before editing.
7. If adding imports, composables, or translated message helpers, check whether the new identifiers can shadow existing local variables, parameters, refs, or computed names in the same file.

## Definition of done

- The change target, dependencies, impact area, failure modes, and validation plan are explicit.
- Hidden higher-level design issues are named if they affect the task.
- Identifier collision risk from newly introduced symbols has been considered when relevant.
