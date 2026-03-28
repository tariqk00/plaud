# Plaud Repository Rules

## Context
This repository automates Plaud.ai recording processing.

## Guidelines

### 1. Global Alignment
- Follow the master constitution in [setup/docs/RULES.md](../../setup/docs/RULES.md).
- Follow infrastructure standards in [setup/docs/ENV_SETUP.md](../../setup/docs/ENV_SETUP.md).

### 2. Python & Environment
- **Virtual Environment**: Always use the local `venv` directory.
- **Dependencies**: Manage via `requirements.txt`.
- **Secrets**: Provide paths to `credentials.json` but do not commit them.

### 3. Change Management
- Update `JOURNAL.md` with every significant change.
- Use conventional commits.
