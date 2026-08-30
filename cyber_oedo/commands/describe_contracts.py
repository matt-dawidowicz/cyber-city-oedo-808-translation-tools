"""Print the versioned external contract catalog as JSON."""

from __future__ import annotations

import argparse
import json

from cyber_oedo.contracts import contracts_document


def build_parser() -> argparse.ArgumentParser:
    """Build the contract-catalog command-line parser."""

    parser = argparse.ArgumentParser(
        description="Print stable CLI file and JSON contract versions."
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON instead of indented JSON",
    )
    return parser


def main() -> None:
    """Serialize the external contract catalog to standard output."""

    args = build_parser().parse_args()
    indent = None if args.compact else 2
    print(
        json.dumps(
            contracts_document(),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
        )
    )


if __name__ == "__main__":
    main()
