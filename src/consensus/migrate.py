"""CLI for copying legacy JSON data into the active data directory."""

from __future__ import annotations

import argparse
import json

from .paths import SOURCE_DATA_DIR, get_data_dir, migrate_legacy_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Safely copy legacy Consensus JSON files into the active data "
            "directory. Existing files are never overwritten or deleted."
        )
    )
    parser.add_argument(
        "--source",
        default=str(SOURCE_DATA_DIR),
        help="Legacy data directory (default: project data directory).",
    )
    parser.add_argument(
        "--target",
        default=str(get_data_dir()),
        help="Destination data directory (default: active data directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be copied without writing anything.",
    )

    args = parser.parse_args(argv)

    report = migrate_legacy_data(
        source=args.source,
        target=args.target,
        dry_run=args.dry_run,
    )

    print(json.dumps(report, indent=2))

    return 1 if report["conflicts"] or report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
