# update-invoices-xmls

## Setup (with uv)

Install [uv](https://docs.astral.sh/uv/) if needed (`curl -LsSf https://astral.sh/uv/install.sh | sh`), then:

```bash
# Create a virtual env and install dependencies (uses uv.lock for reproducible installs)
uv sync
```

Other useful commands:

- **Add a dependency:** `uv add <package>`
- **Run a script:** `uv run python src/main.py` (uses project env automatically)
- **Upgrade all:** `uv lock --upgrade` then `uv sync`