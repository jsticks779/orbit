# Contributing

Thanks for helping make Orbit better!

1. Fork and clone, then follow **Development** in [SETUP.md](SETUP.md).
2. Read [ARCHITECTURE.md](ARCHITECTURE.md). Most contributions are a new action in `src/orbit/actions/`.
3. Add a test in `tests/` and run `.venv/bin/pytest`.
4. Open a pull request with a short description and, for UI changes, a screenshot.

Guidelines:
- Never overwrite the user's files: use `core.naming.output_path`.
- Keep the ring fast: no heavy imports at module level in `actions/`.
- Friendly errors: raise `ActionError` with what the user can do about it.
