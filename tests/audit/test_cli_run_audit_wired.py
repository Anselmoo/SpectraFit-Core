"""Source-level assertion that cli.run calls run_audit on the success path.

This test does NOT run the benchmark — it inspects the source text of the
`run` command to confirm the wiring is in place.  Fast (<0.1 s).
"""

import inspect

import oracles.cli as cli


def test_run_command_calls_run_audit():
    src = inspect.getsource(cli.run)
    assert "run_audit(" in src, "cli.run must call run_audit on the success path"
