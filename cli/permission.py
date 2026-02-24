"""Permission policy engine for the CLI.

Determines whether tool calls need user approval based on the configured policy.
"""

from dataclasses import dataclass


@dataclass
class PermissionPolicy:
    """Permission policy configuration.

    Policies:
        strict: All write/dangerous tools require approval. Default.
        relaxed: Only dangerous tools (bash) require approval.
        yolo: Auto-approve everything. Use at your own risk.
    """

    policy: str = "strict"

    def needs_approval(self, permission_level: str) -> bool:
        """Check if a tool with given permission level needs user approval.

        Args:
            permission_level: "auto", "confirm", or "dangerous".

        Returns:
            True if the tool call should be shown to the user for approval.
        """
        if self.policy == "yolo":
            return False

        if self.policy == "relaxed":
            return permission_level == "dangerous"

        # strict: confirm + dangerous need approval
        return permission_level in ("confirm", "dangerous")
