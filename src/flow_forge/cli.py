"""Command-line entry point."""

import argparse

from flow_forge import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flow-forge")
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args(argv)
    return 0
