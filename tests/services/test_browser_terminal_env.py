"""PTY shell environment helpers."""

from orchestrator.services.browser_terminal import build_pty_shell_environment


def test_build_pty_shell_environment_overrides_dumb_term() -> None:
    env = build_pty_shell_environment(
        {"TERM": "dumb", "STARSHIP_SHELL": "zsh", "HOME": "/tmp"},
        cols=100,
        rows=28,
    )
    assert env["TERM"] == "xterm-256color"
    assert env["COLORTERM"] == "truecolor"
    assert env["TERM_PROGRAM"] == "fluxion"
    assert "STARSHIP_SHELL" not in env
    assert env["COLUMNS"] == "100"
    assert env["LINES"] == "28"
    assert env["HOME"] == "/tmp"
