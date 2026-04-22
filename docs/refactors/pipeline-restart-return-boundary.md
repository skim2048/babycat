# Refactoring Checklist: Pipeline Restart Return Boundary

## 1. Change Summary

- Refactoring target: `app/main.py` pipeline restart entry point
- Main flow: `Camera Apply`
- Reason for change: make the no-op boundary around `restart_pipeline()` explicit without changing runtime behavior

## 2. Responsibility Boundary

- Owner layer: `app`
- Producer: `app/main.py`
- Consumer: `app/server.py`, watchdog restart path, startup comments
- Adjacent layers to review: camera apply success path, pipeline refs publication during boot

## 3. Boundary Preservation Checks

- pipeline refs are still the source of truth for whether restart is possible
- callers may ignore the return value, but the function now states whether restart actually began
- pipeline start/stop behavior remains unchanged

## 4. Minimum Validation

- Required checks from the validation guide: runtime ownership unchanged, restart assumptions explicit
- Automated checks to run: `python -c "import ast, pathlib; ast.parse(pathlib.Path('app/main.py').read_text(encoding='utf-8'))"`
- Manual checks to run: static review of `restart_pipeline()` callers

## 5. Result

- What was validated:
  - `restart_pipeline()` now returns whether restart arguments were ready
  - ref lookup is named explicitly in `_pipeline_restart_args()`
  - `app/main.py` passed a read-only Python AST parse check
- What was not validated:
  - live watchdog or camera-triggered restart on a running system
- Remaining risk:
  - the boundary is clearer, but runtime restart timing still depends on GStreamer and live camera conditions
