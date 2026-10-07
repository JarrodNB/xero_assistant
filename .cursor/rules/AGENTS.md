# Cursor rules

These Markdown rule files apply to every conversation in this repo.

- `rules.mdc` — engineering standards, AI data privacy, and MCP tool rules. It requires an `AGENTS.md` in every folder and a file header whose format is defined by that folder.
- `docker.mdc` — run the app and tests with Docker Compose from the Ubuntu WSL distro. Do not create a host virtualenv or invoke Python on Windows.

Keep a rule here when it applies across the repo. Put folder-specific conventions in that folder's `AGENTS.md`.
