"""CLI configuration from args and config file.

Supports:
- Command-line arguments (highest priority)
- Config file at ~/.config/reasoner/config.toml
- Environment variables
- Sensible defaults
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CLIConfig:
    """CLI configuration."""

    api_url: str = "http://127.0.0.1:9000"
    provider: str = "default"
    model: Optional[str] = None
    mode: str = "agent"
    permission: str = "strict"
    working_dir: str = "."
    max_steps: int = 15
    session_cookie: Optional[str] = None
    session_id: Optional[str] = None  # CLI session ID for ChatGPT auth
    profile: str = "coding"  # CLI always uses coding profile

    @classmethod
    def from_args(
        cls,
        api_url: str = "http://127.0.0.1:9000",
        provider: str = "default",
        model: Optional[str] = None,
        mode: str = "agent",
        permission: str = "strict",
        working_dir: str = ".",
        max_steps: int = 15,
    ) -> "CLIConfig":
        """Create config from CLI arguments.

        Args:
            api_url: Backend URL.
            provider: Provider name (default, chatgpt).
            model: Model name override.
            mode: Chat or agent mode.
            permission: Permission policy.
            working_dir: Working directory for filesystem tools.
            max_steps: Max agent steps.

        Returns:
            CLIConfig instance.
        """
        config = cls(
            api_url=api_url.rstrip("/"),
            provider=provider,
            model=model,
            mode=mode,
            permission=permission,
            working_dir=str(Path(working_dir).resolve()),
            max_steps=max_steps,
        )

        # Try loading saved session from config dir
        config_dir = Path.home() / ".config" / "reasoner"
        cookie_file = config_dir / "session"
        if cookie_file.exists():
            config.session_cookie = cookie_file.read_text().strip()

        session_file = config_dir / "cli_session"
        if session_file.exists():
            config.session_id = session_file.read_text().strip()

        return config

    def save_session(self, cookie: str) -> None:
        """Save session cookie to config directory."""
        config_dir = Path.home() / ".config" / "reasoner"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "session").write_text(cookie)
        self.session_cookie = cookie

    def save_cli_session(self, session_id: str) -> None:
        """Save CLI session ID for ChatGPT auth."""
        config_dir = Path.home() / ".config" / "reasoner"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "cli_session").write_text(session_id)
        self.session_id = session_id

    def clear_cli_session(self) -> None:
        """Clear saved CLI session."""
        config_dir = Path.home() / ".config" / "reasoner"
        session_file = config_dir / "cli_session"
        if session_file.exists():
            session_file.unlink()
        self.session_id = None
