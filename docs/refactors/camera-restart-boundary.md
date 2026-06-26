# Refactoring Checklist: Camera Restart Boundary

## 1. Change Summary

- Refactoring target: `app/server.py` camera apply success path
- Main flow: `Camera Apply`
- Reason for change: make the boundary between successful camera apply and asynchronous pipeline restart explicit without changing the public response contract

## 2. Responsibility Boundary

- Owner layer: `app`
- Producer: `app/server.py`
- Consumer: `api` camera proxy, `web` camera save flow, `main.restart_pipeline()`
- Adjacent layers to review: `app/camera.py`, `docs/api.md`, startup pipeline behavior

## 3. Boundary Preservation Checks

- `camera.apply()` remains the owner of profile normalization, persistence, and runtime source activation
- pipeline restart remains a server-layer follow-up step
- `POST /camera` response shape remains unchanged

## 4. Minimum Validation

- Required checks from the validation guide: current client path still applies the camera profile, apply failure state stays visible, pipeline restart assumptions are explicit
- Automated checks to run: `python -c "import ast, pathlib; ast.parse(pathlib.Path('app/server.py').read_text(encoding='utf-8'))"`
- Manual checks to run: static review that success still schedules restart asynchronously

## 5. Result

- What was validated:
  - `app/server.py` now names the camera-restart scheduling step explicitly
  - `docs/api.md` now states that `{"ok": true}` means restart was scheduled, not synchronously completed
  - `app/server.py` passed a read-only Python AST parse check
- What was not validated:
  - live pipeline restart on a real running app
- Remaining risk:
  - the ownership boundary is clearer, but actual restart timing still depends on runtime conditions in `main.restart_pipeline()`
