# Refactoring Checklist: API Contract Responses

## 1. Change Summary

- Refactoring target: `api` auth response assembly and camera proxy response normalization
- Main flow: `Auth` and `Camera Apply`
- Reason for change: make the `api` layer's external contract role explicit without changing public behavior

## 2. Responsibility Boundary

- Owner layer: `api`
- Producer: `api/main.py` response assembly for auth and camera proxy routes
- Consumer: `web`, `docs/api.md`, `tests/test_api.py`
- Adjacent layers to review: `api/auth.py`, `app` camera endpoints

## 3. Boundary Preservation Checks

- auth response fields and semantics must remain unchanged
- camera profile masking must remain unchanged
- camera apply proxy errors must remain mapped the same way for clients
- upstream `app` ownership must remain intact; `api` continues to normalize the client-facing contract

## 4. Minimum Validation

- Required checks from the validation guide: producer/consumer contract preserved, auth behavior preserved, camera proxy behavior preserved
- Automated checks to run: `python -m pytest tests/test_api.py -q`
- Manual checks to run: static review of response shapes and error mapping

## 5. Result

- What was validated:
  - auth login and refresh response assembly was moved behind helpers without changing response fields
  - camera profile masking remains unchanged for clients
  - upstream camera apply `5xx` responses are still mapped to `502` for clients
  - `python -m pytest tests/test_api.py -q` passed
- What was not validated:
  - full HTTP integration against a running FastAPI server and live `app` container was not exercised
  - browser-visible camera apply behavior was not exercised through `web`
- Remaining risk:
  - this refactor preserves the contract by direct tests and static review, but end-to-end proxy behavior still depends on runtime `app` availability and live container wiring
