"""Tests for agent permission policy classification."""

from orchestrator.agent.permissions import classify_bash_command, classify_tool_call


def test_relaxed_read_only_tool_is_auto_allowed(tmp_path):
    decision = classify_tool_call(
        policy="relaxed",
        tool_name="read_file",
        arguments={"file_path": "app.py"},
        base_permission_level="auto",
        workspace_path=str(tmp_path),
    )

    assert decision.needs_approval is False
    assert decision.permission_level == "auto"


def test_relaxed_write_tool_requires_approval(tmp_path):
    decision = classify_tool_call(
        policy="relaxed",
        tool_name="write_file",
        arguments={"file_path": "app.py", "content": "x"},
        base_permission_level="confirm",
        workspace_path=str(tmp_path),
    )

    assert decision.needs_approval is True
    assert decision.permission_level == "confirm"


def test_relaxed_bash_read_only_command_is_auto_allowed(tmp_path):
    decision = classify_bash_command(
        command="git status && rg permission_policy orchestrator",
        workspace_path=str(tmp_path),
    )

    assert decision.needs_approval is False
    assert decision.permission_level == "auto"


def test_relaxed_bash_mutating_command_requires_approval(tmp_path):
    decision = classify_bash_command(
        command="mkdir -p src && touch src/new.py",
        workspace_path=str(tmp_path),
    )

    assert decision.needs_approval is True
    assert decision.permission_level == "dangerous"


def test_relaxed_bash_destructive_command_is_marked_destructive(tmp_path):
    decision = classify_bash_command(
        command="rm -rf build",
        workspace_path=str(tmp_path),
    )

    assert decision.needs_approval is True
    assert decision.permission_level == "destructive"


def test_relaxed_bash_outside_workspace_requires_approval(tmp_path):
    decision = classify_bash_command(
        command="cat /etc/hosts",
        workspace_path=str(tmp_path),
    )

    assert decision.needs_approval is True
    assert decision.permission_level == "dangerous"


def test_yolo_auto_approves_mutating_tool(tmp_path):
    decision = classify_tool_call(
        policy="yolo",
        tool_name="edit_file",
        arguments={"file_path": "app.py", "old_string": "a", "new_string": "b"},
        base_permission_level="confirm",
        workspace_path=str(tmp_path),
    )

    assert decision.needs_approval is False
    assert decision.permission_level == "auto"


def test_relaxed_apply_patch_requires_approval(tmp_path):
    decision = classify_tool_call(
        policy="relaxed",
        tool_name="apply_patch",
        arguments={"patch": "*** Begin Patch\n*** End Patch"},
        base_permission_level="confirm",
        workspace_path=str(tmp_path),
    )
    assert decision.needs_approval is True
    assert decision.permission_level == "confirm"


def test_relaxed_exec_command_uses_bash_classifier(tmp_path):
    read_only = classify_tool_call(
        policy="relaxed",
        tool_name="exec_command",
        arguments={"cmd": "git status && rg foo ."},
        base_permission_level="dangerous",
        workspace_path=str(tmp_path),
    )
    mutating = classify_tool_call(
        policy="relaxed",
        tool_name="exec_command",
        arguments={"cmd": "touch x"},
        base_permission_level="dangerous",
        workspace_path=str(tmp_path),
    )
    assert read_only.needs_approval is False
    assert mutating.needs_approval is True


def test_relaxed_write_stdin_auto_allowed_after_session_approval(tmp_path):
    decision = classify_tool_call(
        policy="relaxed",
        tool_name="write_stdin",
        arguments={"session_id": 1, "chars": "q"},
        base_permission_level="dangerous",
        workspace_path=str(tmp_path),
    )
    assert decision.needs_approval is False
