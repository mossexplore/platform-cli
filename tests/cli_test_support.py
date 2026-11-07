"""Inject isolated configuration in tests without a public CLI override."""

from pathlib import Path
from unittest.mock import patch


def invoke_with_config(runner, app, config, args, **kwargs):
    with patch("wiserec_cli.config.default_config_path", return_value=Path(config)):
        return runner.invoke(app, args, **kwargs)


def cli_process_args(config, args, script="from wiserec_cli.cli import run; run()"):
    setup = (
        "from pathlib import Path; from wiserec_cli.execution import ExecutionContext, configure; "
        f"configure(ExecutionContext(config_path=Path({str(config)!r})));\n"
    )
    return ["-c", setup + script, *args]
