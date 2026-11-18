"""Regression coverage for process_agents.common.agent's build_parser() --
the -d/--detached/--http/--port/--server CLI surface, mirroring the
neuro-san port's own identical tests/test_cli.py coverage for cli.
build_parser(). Argparse-only; run_web_service itself calls Flask's
blocking app.run(), so (matching this project's existing test depth for
--http/--port) only the parsed-argument shape is asserted here, not the
server actually binding to the overridden host.
"""

import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")

from process_agents.common.agent import build_parser


def test_parser_rejects_http_port_or_server_without_detached():
    parser = build_parser()
    args = parser.parse_args(["--http"])
    assert args.detached is False and args.http is True
    assert not args.detached and (args.http or args.port is not None or args.server is not None)


def test_parser_rejects_server_without_detached():
    parser = build_parser()
    args = parser.parse_args(["-s", "0.0.0.0"])
    assert args.detached is False and args.server == "0.0.0.0"
    assert not args.detached and args.server is not None


def test_parser_accepts_server_with_detached():
    parser = build_parser()
    args = parser.parse_args(["-d", "-s", "0.0.0.0"])
    assert args.detached is True and args.server == "0.0.0.0"


def test_parser_defaults_server_to_none():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.server is None
