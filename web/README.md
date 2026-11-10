# Consensus web interface

A single-page frontend for the existing Consensus pipeline. It runs entirely on
your machine and does not change the Python package, its storage, or its
analysis logic.

The page is served by a small Node bridge (`web/server.mjs`) that:

- serves the static frontend from `web/public/`
- reads existing brief artifacts from `data/` for deep links
- invokes the unchanged CLI (`python -m consensus.main`) for new analyses
- streams pipeline progress back to the page as NDJSON

## Requirements

- Node.js 22 or newer
- The project's Python environment (`.venv`) with dependencies installed

## Run

```bash
# from the project root
node web/server.mjs
```

Open <http://127.0.0.1:4173>.

The bridge looks for `.venv/bin/python` first and falls back to `python3`. The
CLI still needs the usual API keys in `.env` before an analysis can run.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Bind address. Keep it on loopback unless you intend to expose it. |
| `PORT` | `4173` | HTTP port. |
| `CONSENSUS_DATA_DIR` | `<project>/data` | Artifact directory to read and write. |
| `CONSENSUS_PYTHON` | `.venv/bin/python` or `python3` | Python executable used to run the CLI. |

## Routes

| Route | Description |
| --- | --- |
| `GET /api/health` | Liveness plus the resolved data directory and Python path. |
| `GET /api/briefs/:videoId/:questionKey` | One saved brief with metrics, distribution, narrative, and top comments. |
| `POST /api/analyze` | Runs the CLI and streams `started`, `stage`, `meta`, `done`, and `error` events. |

## Notes

- New analyses are written by the CLI to the normal `data/` directories.
- The frontend shows the ten most-liked top-level comments. The CLI terminal
  still prints its usual five.
- Likes are engagement, not agreement. The interface says so wherever they
  appear.
- No npm packages are required.
