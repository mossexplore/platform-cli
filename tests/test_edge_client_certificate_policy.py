import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/windows/edge_client_certificate_policy.py"


def test_generates_policy_for_exact_origins_and_prompts_on_multiple_matches():
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT), "https://Auth.Example.com",
            "https://auth.example.com:443/", "https://sso.example.com:8443",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    policies = json.loads(result.stdout)
    assert policies["PromptOnMultipleMatchingCertificates"] is True
    assert [json.loads(rule) for rule in policies["AutoSelectCertificateForUrls"]] == [
        {"pattern": "https://auth.example.com:443", "filter": {}},
        {"pattern": "https://sso.example.com:8443", "filter": {}},
    ]


@pytest.mark.parametrize("origin", [
    "*",
    "https://[*.]example.com",
    "http://auth.example.com",
    "https://auth.example.com:0",
    "https://auth.example.com:65536",
    "https://auth.example.com:*",
    "https://auth.example.com/login",
    "https://login@auth.example.com",
    "https://auth.example.com?state=example",
])
def test_rejects_values_other_than_exact_https_origins(origin):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), origin],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert result.stdout == ""
