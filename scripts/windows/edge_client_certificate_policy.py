"""Generate managed Edge policy values for trusted certificate-request origins."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from wiserec_cli.edge_policy import (
    AUTO_SELECT, PROMPT_ON_MULTIPLE, certificate_rule, normalize_origin,
)


def parse_origin(value: str) -> str:
    try:
        return normalize_origin(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", nargs="+", type=parse_origin, metavar="HTTPS_ORIGIN")
    origins = parser.parse_args().origin
    policies = {
        AUTO_SELECT: [certificate_rule(origin) for origin in dict.fromkeys(origins)],
        PROMPT_ON_MULTIPLE: True,
    }
    print(json.dumps(policies, indent=2))


if __name__ == "__main__":
    main()
