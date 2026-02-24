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

        # Try loading session cookie from config dir
        config_dir = Path.home() / ".config" / "reasoner"
        cookie_file = config_dir / "session"
        if cookie_file.exists():
            config.session_cookie = cookie_file.read_text().strip()

        return config

    def save_session(self, cookie: str) -> None:
        """Save session cookie to config directory."""
        config_dir = Path.home() / ".config" / "reasoner"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "session").write_text(cookie)
        self.session_cookie = cookie
