# Consensus

Consensus is a YouTube audience-intelligence pipeline. It collects a video's
comments, cleans and analyses them, then uses an LLM-generated framework to
classify **top-level comments** against your research question.

The pipeline produces four classification artifacts per video and question:

1. individual classification results
2. an aggregation summary
3. the generated classification framework
4. run metadata (signature, model settings, token/request metrics)

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- API keys for:
  - YouTube Data API v3 (`YOUTUBE_API_KEY`)
  - SubQ (`SUBQ_API_KEY`)
  - Groq (`GROQ_API_KEY`)

## Installation

From a source checkout:

```bash
uv sync
```

Or install the package:

```bash
uv pip install .
# or
pip install .
```

Both the CLI and a data-migration helper are installed as console scripts:

```bash
consensus
consensus-migrate --help
```

## Environment setup

Copy the example file and add your keys:

```bash
cp .env.example .env
```

```dotenv
YOUTUBE_API_KEY=...
SUBQ_API_KEY=...
GROQ_API_KEY=...
```

`.env` is ignored by Git. Never commit real keys. The application loads the
file lazily at runtime, so importing the package never requires credentials.
Source checkouts read `<project>/.env`; an installed package reads the
per-user config directory (for example `~/.config/consensus/.env` on Linux).
Set `CONSENSUS_ENV_FILE` to point at a specific file.

Environment variables may also be exported directly. Real environment
variables take precedence over values in `.env`.

### Optional overrides

| Variable | Purpose |
| --- | --- |
| `CONSENSUS_DATA_DIR` | Use a custom data directory. Highest priority. |
| `CONSENSUS_ENV_FILE` | Load credentials from a specific `.env` file. |

## Where data is stored

The active data directory depends on how Consensus is run:

- **Source checkout:** `<project>/data`
- **Installed package:** the platform user-data directory
  (`~/.local/share/consensus` on Linux, `~/Library/Application Support/consensus`
  on macOS, `%LOCALAPPDATA%\consensus` on Windows)
- **`CONSENSUS_DATA_DIR` set:** that directory, always

The tree contains:

```text
data/
  raw/              # raw YouTube API responses
  processed/        # cleaned comments
  analysis/         # engagement statistics
  classifications/  # results, aggregation, framework, metadata, checkpoints
```

## Migrating existing data

If you previously stored data inside `src/consensus/data`, copy it safely:

```bash
consensus-migrate --dry-run   # show what would be copied
consensus-migrate             # copy with hash verification
```

Migration rules:

- existing target files are **never overwritten**
- identical files are skipped
- conflicting files are reported, not replaced
- source files are never deleted
- every copied file is hash-verified

Use `--source` and `--target` to migrate between custom locations.

## Usage

Run the interactive pipeline:

```bash
consensus
```

You will be asked for:

1. a YouTube URL (`watch`, `shorts`, `embed`, `live`, `youtu.be`)
2. a research question

The pipeline then:

1. validates the video ID
2. fetches video details and comments (with bounded retries)
3. saves raw data
4. cleans comments
5. computes engagement statistics
6. classifies top-level comments
7. writes the four classification artifacts

### Classification population

Only **top-level comments** are classified. Replies are collected, counted and
reported, but they are not sent to the classifier. This preserves the existing
methodology.

### Resume behaviour

Runs resume automatically when the video, research question, comment set,
framework, prompts, models and classification settings all match the saved run
signature. A checkpoint journal is appended after every successful batch, so an
interrupted run does not lose completed work.

If a batch fails, successful batches are still checkpointed and the run exits
with a clear error. Re-running the same question resumes from the journal.

Different research questions for the same video are stored under separate
question-keyed filenames and never overwrite each other. If the inputs for the
same question change, the previous artifacts are archived (hash-verified copy)
before the new run writes its files.

## Output artifacts

For a video `VIDEOID` and question key `KEY`:

```text
data/classifications/
  VIDEOID_KEY.json                      # individual results
  VIDEOID_KEY_aggregation.json          # aggregation summary
  VIDEOID_KEY_framework.json            # classification framework
  VIDEOID_KEY_run_metadata.json         # run metadata
  VIDEOID_KEY_<signature>.jsonl         # append-only checkpoint journal
```

## Development

```bash
uv sync --group dev
uv run pytest
```

Tests mock all providers and never make paid API requests.

## Security notes

- API keys are read lazily and are redacted from error messages.
- YouTube video IDs are validated before being used in file paths or API calls.
- Terminal control characters are stripped from untrusted comment text.
- Comment text is passed to models as quoted, untrusted data with explicit
  instructions not to follow instructions found inside comments.
