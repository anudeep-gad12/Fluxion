"""GAIA Benchmark CLI Entry Point.

Usage:
    python -m scripts.gaia --level 1 --mode agent
    python -m scripts.gaia --level 1 --mode chat
    python -m scripts.gaia --level 1 --compare
    python -m scripts.gaia --level 1 --limit 10
    python -m scripts.gaia --level 1 --concurrency 3  # 3x faster
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.gaia.runner import RunConfig, run_evaluation


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="GAIA Benchmark Evaluation for Reasoner Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run agent mode on Level 1
    python -m scripts.gaia --level 1 --mode agent

    # Run chat mode on Level 1
    python -m scripts.gaia --level 1 --mode chat

    # Compare agent vs chat
    python -m scripts.gaia --level 1 --compare

    # Quick test with 5 questions
    python -m scripts.gaia --level 1 --limit 5

    # Run 3 questions in parallel (3x faster)
    python -m scripts.gaia --level 1 -c 3

    # Run all Level 1 questions
    HF_TOKEN=xxx python -m scripts.gaia --level 1 --compare
        """,
    )

    parser.add_argument(
        "--level",
        type=int,
        default=1,
        choices=[1, 2, 3],
        help="GAIA difficulty level (default: 1)",
    )

    parser.add_argument(
        "--split",
        type=str,
        default="validation",
        choices=["validation", "test"],
        help="Dataset split (default: validation)",
    )

    parser.add_argument(
        "--mode",
        type=str,
        default="agent",
        choices=["agent", "chat"],
        help="Evaluation mode (default: agent)",
    )

    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run both agent and chat modes for comparison",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of questions (for testing)",
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=10,
        help="Maximum agent steps (default: 10)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout per question in seconds (default: 300)",
    )

    parser.add_argument(
        "--include-attachments",
        action="store_true",
        help="Include questions with file attachments (skipped by default)",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./gaia_results"),
        help="Output directory for results (default: ./gaia_results)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    parser.add_argument(
        "--api-url",
        type=str,
        default=os.environ.get("API_URL", "http://127.0.0.1:9000"),
        help="API server URL (default: http://127.0.0.1:9000)",
    )

    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=1,
        help="Number of parallel evaluations (default: 1, sequential)",
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Check for HF_TOKEN or HUGGING_FACE
    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE")
    if not hf_token:
        print("Error: HF_TOKEN or HUGGING_FACE environment variable required")
        print("Get token from https://huggingface.co/settings/tokens")
        print("Then set: export HF_TOKEN=your_token")
        return 1

    # Determine mode
    mode = "compare" if args.compare else args.mode

    # Build config
    config = RunConfig(
        level=args.level,
        split=args.split,
        mode=mode,
        limit=args.limit,
        max_steps=args.max_steps,
        timeout_seconds=args.timeout,
        skip_attachments=not args.include_attachments,
        output_dir=args.output_dir,
        hf_token=hf_token,
        verbose=not args.quiet,
        api_url=args.api_url,
        concurrency=args.concurrency,
    )

    if not args.quiet:
        print("=" * 60)
        print("GAIA Benchmark Evaluation")
        print("=" * 60)
        print(f"Level: {config.level}")
        print(f"Split: {config.split}")
        print(f"Mode: {config.mode}")
        print(f"API: {config.api_url}")
        if config.concurrency > 1:
            print(f"Concurrency: {config.concurrency} parallel")
        if config.limit:
            print(f"Limit: {config.limit} questions")
        print("=" * 60)

    try:
        results = await run_evaluation(config)
        return 0

    except ImportError as e:
        print(f"Error: {e}")
        print("\nInstall benchmark dependencies with:")
        print("  uv sync --extra benchmark")
        return 1

    except EnvironmentError as e:
        print(f"Error: {e}")
        return 1

    except KeyboardInterrupt:
        print("\nEvaluation cancelled by user")
        return 130

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
