"""Prompt loading utilities.

Loads system prompts from files or uses inline defaults.
File paths take precedence over inline strings.
"""

from pathlib import Path
from typing import Optional

from orchestrator.config import PROMPTS_DIR, SystemPromptConfig


class PromptLoader:
    """Loads system prompts from files or config.

    Prompts can be:
    1. Loaded from files (for easy iteration without code changes)
    2. Defined inline in SystemPromptConfig

    File paths take precedence over inline strings.
    """

    def __init__(self, prompts_dir: Path = PROMPTS_DIR):
        """Initialize the prompt loader.

        Args:
            prompts_dir: Directory containing prompt files.
        """
        self.prompts_dir = prompts_dir
        self._cache: dict[str, str] = {}

    def load(self, config: SystemPromptConfig, prompt_type: str) -> str:
        """Load a prompt by type.

        Args:
            config: System prompt configuration.
            prompt_type: Type of prompt ('reasoning', 'chat', etc.)

        Returns:
            The prompt string.

        Raises:
            ValueError: If prompt_type is not recognized.
        """
        path_attr = f"{prompt_type}_prompt_path"
        inline_attr = f"{prompt_type}_prompt"

        # Check if path attribute exists on config
        if not hasattr(config, inline_attr):
            raise ValueError(f"Unknown prompt type: {prompt_type}")

        # Try to load from file path first
        path: Optional[Path] = getattr(config, path_attr, None)
        if path is not None:
            # Handle relative paths
            if not path.is_absolute():
                path = self.prompts_dir / path
            if path.exists():
                return self._load_file(path)

        # Fall back to inline string
        return getattr(config, inline_attr)

    def load_reasoning_prompt(self, config: SystemPromptConfig) -> str:
        """Load the reasoning prompt.

        Args:
            config: System prompt configuration.

        Returns:
            The reasoning prompt string.
        """
        return self.load(config, "reasoning")

    def load_chat_prompt(self, config: SystemPromptConfig) -> str:
        """Load the chat prompt.

        Args:
            config: System prompt configuration.

        Returns:
            The chat prompt string.
        """
        return self.load(config, "chat")

    def _load_file(self, path: Path) -> str:
        """Load prompt from file with caching.

        Args:
            path: Path to the prompt file.

        Returns:
            The file contents.
        """
        cache_key = str(path)
        if cache_key not in self._cache:
            self._cache[cache_key] = path.read_text(encoding="utf-8")
        return self._cache[cache_key]

    def clear_cache(self) -> None:
        """Clear the prompt cache."""
        self._cache.clear()


# Singleton instance
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """Get the singleton PromptLoader instance."""
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader
