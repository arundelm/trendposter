# Contributing to TrendPoster

Thanks for your interest in contributing!

## Setup for development

```bash
git clone https://github.com/arundelm/trendposter.git
cd trendposter
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all,dev]"
```

## Running tests

```bash
pytest
```

## Code style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
ruff check .
ruff format .
```

## Adding a new LLM provider

1. Create a class in `trendposter/llm/providers.py` that extends `BaseLLMProvider`
2. Implement the `complete(prompt: str) -> str` method
3. Add it to `PROVIDER_MAP` in `trendposter/llm/__init__.py`
4. Add the env var to `PROVIDER_KEY_VARS` in `trendposter/config.py`
5. Add the dependency to `pyproject.toml` optional deps
6. Update `README.md` and `.env.example`

## Adding a new bot platform

1. Create a new file in `trendposter/bot/`
2. Implement the same command set (queue, list, remove, trends, analyze, post, status)
3. Wire it into `trendposter/cli.py`
4. Update `README.md`

## Pull requests

- Keep PRs focused on a single change
- Add tests for new functionality
- Update docs if needed
- Run `ruff check .` before submitting
