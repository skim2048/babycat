# Babycat Refactoring Checklist Template

Use this checklist for each refactoring task after identifying the target flow in [refactoring-validation-guide.md](refactoring-validation-guide.md).

## Checklist

### 1. Change Summary

- Refactoring target:
- Main flow:
- Reason for change:

### 2. Responsibility Boundary

- Owner layer:
- Producer:
- Consumer:
- Adjacent layers to review:

### 3. Boundary Preservation Checks

- Which contract or runtime assumption must remain unchanged?
- Which file, config, or endpoint remains the source of truth?
- Which neighboring layer could be affected silently?

### 4. Minimum Validation

- Required checks from the validation guide:
- Automated checks to run:
- Manual checks to run:

### 5. Result

- What was validated:
- What was not validated:
- Remaining risk:

## Short Form

Use this shorter form in small refactors.

```md
Flow:
Owner:
Producer:
Consumer:
Checks:
Validated:
Remaining risk:
```
