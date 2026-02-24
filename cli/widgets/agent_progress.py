"""Agent step progress indicator."""

from textual.widgets import Static


class AgentProgress(Static):
    """Shows current step N/M progress for agent execution.

    Styling is handled by the app.tcss file.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._current_step = 0
        self._max_steps = 0

    def update_step(self, step: int, max_steps: int = 0) -> None:
        """Update the progress display."""
        self._current_step = step
        if max_steps:
            self._max_steps = max_steps

        if self._max_steps:
            text = f" Step {step}/{self._max_steps}"
        else:
            text = f" Step {step}"

        self.update(text)
        self.add_class("visible")

    def reset(self) -> None:
        """Reset progress display."""
        self._current_step = 0
        self._max_steps = 0
        self.update("")
        self.remove_class("visible")
