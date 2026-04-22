---
name: babycat-test-selection
description: Use after implementation to choose, run, and report the smallest credible mix of automated tests and manual checks based on the affected layer, contract, and runtime risk.
---

# babycat-test-selection

## When to use

- After implementing a change.
- When choosing, running, and reporting validation for the affected layer.

## Do not use when

- No implementation was made.
- The task is only exploratory analysis with no changed behavior.

## Steps

1. Classify the change as `app`, `api`, `web`, or cross-boundary.
2. Choose the smallest validation set that matches the changed contract.
3. Prefer focused existing tests first, then add manual checks for uncovered flows.
4. Record what was run, what was not run, and why.
5. Avoid claiming full coverage when hardware or streaming paths were not exercised.
6. Report both validated behavior and remaining runtime risk.

## Definition of done

- A right-sized validation set was chosen, run when possible, and reported.
- Any gap between performed validation and runtime risk is explicit.
