"""Codex-style browser Plan Mode primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

CollaborationMode = Literal["default", "plan"]

PLAN_MODE_INSTRUCTIONS = """
<collaboration_mode>
# Collaboration Mode: Plan

You are in Plan Mode. Your job is to understand the user's request, inspect the
workspace as needed, ask for high-impact decisions when needed, and produce a
decision-complete implementation plan.

Plan Mode rules:
- Explore before asking. Prefer read-only tools to discover repo facts.
- Do not modify files, run tests, run shell commands, execute Python, apply
  patches, or perform any action that carries out the implementation.
- When `update_plan_doc` is available, keep the assigned durable markdown plan
  document current with research notes, assumptions, open questions, draft
  plan, and checklist updates. This is the only file write allowed in Plan Mode.
- Use `request_user_input` for important product/implementation choices that
  cannot be discovered from the repo.
- Keep iterating when the user rejects a plan. Treat rejection feedback as
  guidance and continue planning.
- Finalize by outputting exactly one proposed plan wrapped in:
  <proposed_plan>
  ...
  </proposed_plan>

The proposed plan should be concise, implementation-ready, and include:
- title and summary,
- key backend/frontend/interface changes,
- plan approval/transition behavior when relevant,
- tests and validation,
- assumptions.
</collaboration_mode>
""".strip()

PLAN_MODE_MUTATING_TOOLS = {
    "apply_patch",
    "edit_file",
    "write_file",
    "exec_command",
    "write_stdin",
    "bash",
    "python_execute",
}

_PROPOSED_PLAN_RE = re.compile(
    r"<proposed_plan>\s*(?P<plan>.*?)\s*</proposed_plan>",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class ProposedPlan:
    """Parsed proposed plan block."""

    markdown: str
    visible_answer: str


@dataclass
class PlanDecision:
    """User decision for a proposed plan."""

    decision: Literal["approved", "rejected"]
    feedback: Optional[str] = None
    implementation_run_id: Optional[str] = None
    implementation_stream_token: Optional[str] = None


def normalize_collaboration_mode(mode: Optional[str]) -> CollaborationMode:
    """Normalize unknown collaboration modes to default."""
    return "plan" if mode == "plan" else "default"


def extract_proposed_plan(text: str) -> Optional[ProposedPlan]:
    """Extract the first proposed plan block and strip all plan markup."""
    match = _PROPOSED_PLAN_RE.search(text or "")
    if not match:
        return None

    markdown = match.group("plan").strip()
    visible_answer = _PROPOSED_PLAN_RE.sub("", text or "", count=1).strip()
    return ProposedPlan(markdown=markdown, visible_answer=visible_answer)


def build_plan_rejection_message(feedback: Optional[str]) -> str:
    """Build the model-facing feedback message after a plan rejection."""
    clean_feedback = (feedback or "").strip()
    if clean_feedback:
        return (
            "The user rejected the proposed plan. Continue planning in Plan Mode "
            "and revise it using this feedback:\n\n"
            f"{clean_feedback}"
        )
    return (
        "The user rejected the proposed plan. Continue planning in Plan Mode. "
        "Inspect more context or ask focused questions if needed, then produce a revised plan."
    )


def build_plan_implementation_prompt(
    plan_markdown: str,
    plan_doc_path: Optional[str] = None,
) -> str:
    """Build the Default Mode handoff prompt for implementing an approved plan."""
    plan_doc_note = ""
    if plan_doc_path:
        plan_doc_note = (
            f"\n\nApproved plan file: `{plan_doc_path}`. Re-read repository files before "
            "editing; do not rely on stale Plan Mode tool outputs. Fluxion will append "
            "implementation progress to that plan file from run events."
        )
    return (
        "A previous agent produced the plan below to accomplish the user's task. "
        "Implement the plan in a fresh context. Treat the plan as the source of "
        "user intent, re-read files as needed, and carry the work through "
        "implementation and verification.\n\n"
        f"{plan_markdown.strip()}"
        f"{plan_doc_note}"
    )
