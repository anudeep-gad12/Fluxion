"""Tests for browser-displayable tool result payload extraction."""

import json

from orchestrator.agent.tool_result_payloads import (
    bash_output_from_result_data,
    display_result_data,
    parse_stored_result_detail,
)


def test_edit_file_dict_result_extracts_diff():
    diff = "--- a/app.py\n+++ b/app.py\n-old\n+new\n"

    result = display_result_data(
        "edit_file",
        {"file_path": "app.py", "diff": diff, "matched_by": "exact"},
    )

    assert result == diff


def test_write_file_string_result_keeps_diff():
    diff = "--- a/new.py\n+++ b/new.py\n+print('hi')\n"

    assert display_result_data("write_file", diff) == diff


def test_stored_result_detail_round_trips_edit_payload():
    diff = "--- a/app.py\n+++ b/app.py\n-old\n+new\n"
    payload = parse_stored_result_detail(json.dumps({"diff": diff}))

    assert display_result_data("edit_file", payload) == diff


def test_artifact_payload_display_round_trips_json():
    payload = {"artifact_path": ".fluxion/runs/run-1/output.txt", "content": "hello"}

    result = display_result_data("read_artifact", payload)

    assert json.loads(result) == payload


def test_bash_output_extracts_structured_payload():
    output = bash_output_from_result_data(
        {"stdout": "ok\n", "stderr": "", "exit_code": 0, "timed_out": False}
    )

    assert output == {
        "stdout": "ok\n",
        "stderr": "",
        "exit_code": 0,
        "truncated": False,
    }
