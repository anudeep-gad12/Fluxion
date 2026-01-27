"""Benchmarks routes - GAIA evaluation traces."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from orchestrator.logging_config import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


# Path to GAIA results directory
GAIA_RESULTS_DIR = Path(__file__).parent.parent.parent / "gaia_results"


@router.get("/traces")
async def list_traces() -> list[dict[str, Any]]:
    """List all available GAIA evaluation traces.

    Returns:
        List of trace metadata sorted by timestamp (newest first)
    """
    if not GAIA_RESULTS_DIR.exists():
        logger.warning(f"GAIA results directory not found: {GAIA_RESULTS_DIR}")
        return []

    traces = []
    for trace_file in GAIA_RESULTS_DIR.glob("*.json"):
        try:
            with open(trace_file, "r") as f:
                data = json.load(f)
                metadata = data.get("metadata", {})
                summary = data.get("summary", {})

                traces.append({
                    "filename": trace_file.name,
                    "timestamp": metadata.get("timestamp"),
                    "level": metadata.get("level"),
                    "model": metadata.get("model_name"),
                    "total_questions": summary.get("total_questions", 0),
                    "correct": summary.get("agent_correct", 0),
                    "accuracy": summary.get("agent_accuracy", 0.0),
                })
        except Exception as e:
            logger.warning(f"Failed to read trace file {trace_file.name}: {e}")
            continue

    # Sort by timestamp descending (newest first)
    traces.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return traces


@router.get("/traces/{filename}")
async def get_trace(filename: str) -> dict[str, Any]:
    """Get full trace data for a specific evaluation run.

    Args:
        filename: Name of the trace file

    Returns:
        Complete trace data including metadata, summary, and results
    """
    # Security: prevent path traversal
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    trace_file = GAIA_RESULTS_DIR / filename

    if not trace_file.exists():
        raise HTTPException(status_code=404, detail="Trace not found")

    try:
        with open(trace_file, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read trace file {filename}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read trace")
