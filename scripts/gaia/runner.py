"""GAIA Benchmark Runner.

Runs the GAIA benchmark evaluation against the reasoner agent.
Requires the API server to be running on port 9000.

Usage:
    from scripts.gaia.runner import run_evaluation
    results = await run_evaluation(level=1, mode="agent")
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import httpx

from .loader import GAIAQuestion, load_gaia_dataset
from .scorer import ScoreResult, score_answer, extract_answer_with_llm
from .results import (
    EvaluationResults,
    aggregate_results,
    save_results,
    save_markdown_report,
    format_summary,
)


# Default API URL (can be overridden via environment variable)
DEFAULT_API_URL = "http://127.0.0.1:9000"


@dataclass
class RunConfig:
    """Configuration for benchmark run.

    Attributes:
        level: GAIA difficulty level (1, 2, or 3).
        split: Dataset split ("validation" or "test").
        mode: Evaluation mode ("agent", "chat", or "compare").
        limit: Maximum number of questions (None for all).
        max_steps: Maximum agent steps.
        timeout_seconds: Timeout per question.
        skip_attachments: Skip questions with file attachments.
        output_dir: Directory for output files.
        hf_token: HuggingFace token.
        verbose: Print progress to console.
        api_url: API server URL.
        concurrency: Number of parallel evaluations (1 = sequential).
    """
    level: int = 1
    split: str = "validation"
    mode: str = "agent"
    limit: Optional[int] = None
    max_steps: int = 10
    timeout_seconds: int = 600  # 10 minutes - complex questions need more time
    skip_attachments: bool = True
    output_dir: Path = Path("./gaia_results")
    hf_token: Optional[str] = None
    verbose: bool = True
    api_url: str = DEFAULT_API_URL
    concurrency: int = 1


async def check_api_health(api_url: str) -> bool:
    """Check if the API server is running.

    Args:
        api_url: Base URL of the API server.

    Returns:
        True if API is healthy, False otherwise.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{api_url}/api/health", timeout=5.0)
            return response.status_code == 200
    except Exception:
        return False


async def run_agent_query(
    query: str,
    max_steps: int = 10,
    timeout_seconds: int = 300,
    api_url: str = DEFAULT_API_URL,
) -> tuple[Optional[str], int, int]:
    """Run a single query through the agent via HTTP API.

    Args:
        query: The question to ask.
        max_steps: Maximum agent steps.
        timeout_seconds: Timeout in seconds.
        api_url: API server URL.

    Returns:
        Tuple of (answer, steps, time_ms).
    """
    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds + 10)) as client:
            # Create agent run via HTTP API
            create_response = await client.post(
                f"{api_url}/api/agent/runs",
                json={
                    "query": query,
                    "max_steps": max_steps,
                },
            )

            if create_response.status_code != 200:
                print(f"  Error creating run: {create_response.text}")
                elapsed_ms = int((time.time() - start_time) * 1000)
                return None, 0, elapsed_ms

            run_data = create_response.json()
            run_id = run_data.get("run_id")

            if not run_id:
                print("  Error: No run_id returned")
                elapsed_ms = int((time.time() - start_time) * 1000)
                return None, 0, elapsed_ms

            # Poll for completion
            poll_interval = 2.0
            max_polls = int(timeout_seconds / poll_interval) + 1

            for _ in range(max_polls):
                status_response = await client.get(f"{api_url}/api/agent/runs/{run_id}")

                if status_response.status_code != 200:
                    await asyncio.sleep(poll_interval)
                    continue

                status_data = status_response.json()
                status = status_data.get("status")

                if status == "succeeded":
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    answer = status_data.get("final_answer")
                    steps = status_data.get("total_steps", 0)
                    return answer, steps, elapsed_ms

                elif status == "failed":
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    error = status_data.get("error_message", "Unknown error")
                    print(f"  Run failed: {error}")
                    return None, status_data.get("total_steps", 0), elapsed_ms

                await asyncio.sleep(poll_interval)

            # Timeout
            elapsed_ms = int((time.time() - start_time) * 1000)
            return None, 0, elapsed_ms

    except asyncio.TimeoutError:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return None, 0, elapsed_ms

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        print(f"  Error: {e}")
        return None, 0, elapsed_ms


async def run_chat_query(
    query: str,
    timeout_seconds: int = 300,
    api_url: str = DEFAULT_API_URL,
) -> tuple[Optional[str], int]:
    """Run a single query through chat mode via HTTP API.

    Args:
        query: The question to ask.
        timeout_seconds: Timeout in seconds.
        api_url: API server URL.

    Returns:
        Tuple of (answer, time_ms).
    """
    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds + 10)) as client:
            # Create a conversation for this query
            conv_response = await client.post(
                f"{api_url}/api/conversations",
                json={"title": "GAIA Benchmark"},
            )

            if conv_response.status_code != 200:
                print(f"  Error creating conversation: {conv_response.text}")
                elapsed_ms = int((time.time() - start_time) * 1000)
                return None, elapsed_ms

            conv_data = conv_response.json()
            conversation_id = conv_data.get("conversation_id")

            if not conversation_id:
                print("  Error: No conversation_id returned")
                elapsed_ms = int((time.time() - start_time) * 1000)
                return None, elapsed_ms

            # Create chat run
            run_response = await client.post(
                f"{api_url}/api/conversations/{conversation_id}/runs",
                json={"message": query},
            )

            if run_response.status_code != 200:
                print(f"  Error creating run: {run_response.text}")
                elapsed_ms = int((time.time() - start_time) * 1000)
                return None, elapsed_ms

            run_data = run_response.json()
            run_id = run_data.get("run_id")

            if not run_id:
                print("  Error: No run_id returned")
                elapsed_ms = int((time.time() - start_time) * 1000)
                return None, elapsed_ms

            # Poll for completion
            poll_interval = 2.0
            max_polls = int(timeout_seconds / poll_interval) + 1

            for _ in range(max_polls):
                status_response = await client.get(f"{api_url}/api/runs/{run_id}")

                if status_response.status_code != 200:
                    await asyncio.sleep(poll_interval)
                    continue

                status_data = status_response.json()
                status = status_data.get("status")

                if status == "succeeded":
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    answer = status_data.get("final_answer")
                    return answer, elapsed_ms

                elif status == "failed":
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    error = status_data.get("error_message", "Unknown error")
                    print(f"  Run failed: {error}")
                    return None, elapsed_ms

                await asyncio.sleep(poll_interval)

            # Timeout
            elapsed_ms = int((time.time() - start_time) * 1000)
            return None, elapsed_ms

    except asyncio.TimeoutError:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return None, elapsed_ms

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        print(f"  Error: {e}")
        return None, elapsed_ms


async def evaluate_single_question(
    index: int,
    question: GAIAQuestion,
    mode: str,
    max_steps: int,
    timeout_seconds: int,
    api_url: str,
    semaphore: asyncio.Semaphore,
) -> tuple[int, Optional[str], int, int, Optional[ScoreResult]]:
    """Evaluate a single question with semaphore for concurrency control.

    Args:
        index: Question index (for ordering results).
        question: The question to evaluate.
        mode: "agent" or "chat".
        max_steps: Maximum agent steps.
        timeout_seconds: Timeout per question.
        api_url: API server URL.
        semaphore: Semaphore for concurrency limiting.

    Returns:
        Tuple of (index, answer, time_ms, steps, score).
    """
    async with semaphore:
        if mode == "agent":
            raw_answer, step_count, time_ms = await run_agent_query(
                question.question,
                max_steps=max_steps,
                timeout_seconds=timeout_seconds,
                api_url=api_url,
            )
        else:
            raw_answer, time_ms = await run_chat_query(
                question.question,
                timeout_seconds=timeout_seconds,
                api_url=api_url,
            )
            step_count = 0

        # Use LLM to extract clean answer from verbose response
        if raw_answer:
            answer = await extract_answer_with_llm(
                response=raw_answer,
                question=question.question,
                api_url=api_url,
            )
        else:
            answer = raw_answer

        # Score the answer
        score = None
        if question.final_answer:
            score = score_answer(
                predicted=answer,
                ground_truth=question.final_answer,
                task_id=question.task_id,
            )

        return index, answer, time_ms, step_count, score


async def evaluate_questions(
    questions: List[GAIAQuestion],
    mode: str,
    max_steps: int = 10,
    timeout_seconds: int = 300,
    api_url: str = DEFAULT_API_URL,
    concurrency: int = 1,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> tuple[List[ScoreResult], List[Optional[str]], List[int], List[int]]:
    """Evaluate a list of questions.

    Args:
        questions: Questions to evaluate.
        mode: "agent" or "chat".
        max_steps: Maximum agent steps.
        timeout_seconds: Timeout per question.
        api_url: API server URL.
        concurrency: Number of parallel evaluations.
        progress_callback: Optional callback(current, total, status).

    Returns:
        Tuple of (scores, answers, times, steps).
    """
    if concurrency <= 1:
        # Sequential evaluation (original behavior)
        scores: List[ScoreResult] = []
        answers: List[Optional[str]] = []
        times: List[int] = []
        steps: List[int] = []

        for i, question in enumerate(questions):
            if progress_callback:
                progress_callback(i + 1, len(questions), f"Evaluating: {question.task_id}")

            if mode == "agent":
                raw_answer, step_count, time_ms = await run_agent_query(
                    question.question,
                    max_steps=max_steps,
                    timeout_seconds=timeout_seconds,
                    api_url=api_url,
                )
                steps.append(step_count)
            else:
                raw_answer, time_ms = await run_chat_query(
                    question.question,
                    timeout_seconds=timeout_seconds,
                    api_url=api_url,
                )
                steps.append(0)

            # Use LLM to extract clean answer
            if raw_answer:
                answer = await extract_answer_with_llm(
                    response=raw_answer,
                    question=question.question,
                    api_url=api_url,
                )
            else:
                answer = raw_answer

            answers.append(answer)
            times.append(time_ms)

            # Score the answer
            if question.final_answer:
                result = score_answer(
                    predicted=answer,
                    ground_truth=question.final_answer,
                    task_id=question.task_id,
                )
                scores.append(result)

                if progress_callback:
                    status = "CORRECT" if result.correct else "INCORRECT"
                    progress_callback(i + 1, len(questions), f"{question.task_id}: {status}")

        return scores, answers, times, steps

    # Parallel evaluation
    semaphore = asyncio.Semaphore(concurrency)
    completed_count = 0

    async def run_with_progress(idx: int, q: GAIAQuestion):
        nonlocal completed_count
        result = await evaluate_single_question(
            idx, q, mode, max_steps, timeout_seconds, api_url, semaphore
        )
        completed_count += 1
        if progress_callback:
            _, answer, _, _, score = result
            if score:
                status = "CORRECT" if score.correct else "INCORRECT"
                progress_callback(completed_count, len(questions), f"{q.task_id}: {status}")
            else:
                progress_callback(completed_count, len(questions), f"Completed: {q.task_id}")
        return result

    # Run all questions in parallel (limited by semaphore)
    tasks = [run_with_progress(i, q) for i, q in enumerate(questions)]
    results = await asyncio.gather(*tasks)

    # Sort results by original index and extract components
    results.sort(key=lambda x: x[0])

    scores = []
    answers = []
    times = []
    steps = []

    for _, answer, time_ms, step_count, score in results:
        answers.append(answer)
        times.append(time_ms)
        steps.append(step_count)
        if score:
            scores.append(score)

    return scores, answers, times, steps


async def run_evaluation(config: RunConfig) -> EvaluationResults:
    """Run GAIA benchmark evaluation.

    Args:
        config: Run configuration.

    Returns:
        EvaluationResults with all data.
    """
    # Check API health first
    if not await check_api_health(config.api_url):
        raise EnvironmentError(
            f"API server not reachable at {config.api_url}\n"
            "Start the server with: ./dev.sh start"
        )

    # Load dataset
    if config.verbose:
        print(f"\nLoading GAIA Level {config.level} {config.split} set...")

    questions = load_gaia_dataset(
        level=config.level,
        split=config.split,
        hf_token=config.hf_token,
        skip_attachments=config.skip_attachments,
    )

    if config.limit:
        questions = questions[:config.limit]

    if config.verbose:
        print(f"Loaded {len(questions)} questions")

    # Get model name for metadata
    try:
        async with httpx.AsyncClient() as client:
            config_response = await client.get(f"{config.api_url}/api/config")
            if config_response.status_code == 200:
                api_config = config_response.json()
                model_name = api_config.get("config", {}).get("model", {}).get("name", "unknown")
            else:
                model_name = "unknown"
    except Exception:
        model_name = "unknown"

    # Run evaluation based on mode
    agent_scores = None
    chat_scores = None
    agent_answers = None
    chat_answers = None
    agent_times = None
    chat_times = None
    agent_steps = None

    def print_progress(current: int, total: int, status: str):
        if config.verbose:
            print(f"[{current}/{total}] {status}")

    if config.mode in ("agent", "compare"):
        if config.verbose:
            mode_str = f"Agent mode (concurrency={config.concurrency})" if config.concurrency > 1 else "Agent mode"
            print(f"\nRunning {mode_str} evaluation...")

        agent_scores, agent_answers, agent_times, agent_steps = await evaluate_questions(
            questions,
            mode="agent",
            max_steps=config.max_steps,
            timeout_seconds=config.timeout_seconds,
            api_url=config.api_url,
            concurrency=config.concurrency,
            progress_callback=print_progress,
        )

    if config.mode in ("chat", "compare"):
        if config.verbose:
            mode_str = f"Chat mode (concurrency={config.concurrency})" if config.concurrency > 1 else "Chat mode"
            print(f"\nRunning {mode_str} evaluation...")

        chat_scores, chat_answers, chat_times, _ = await evaluate_questions(
            questions,
            mode="chat",
            timeout_seconds=config.timeout_seconds,
            api_url=config.api_url,
            concurrency=config.concurrency,
            progress_callback=print_progress,
        )

    # Aggregate results
    results = aggregate_results(
        questions=questions,
        agent_scores=agent_scores,
        chat_scores=chat_scores,
        agent_times=agent_times,
        chat_times=chat_times,
        agent_steps=agent_steps,
        agent_answers=agent_answers,
        chat_answers=chat_answers,
        level=config.level,
        split=config.split,
        model_name=model_name,
        max_steps=config.max_steps,
    )

    # Print summary
    if config.verbose:
        print(format_summary(results))

    # Save results (JSON and Markdown)
    timestamp = results.metadata.timestamp.replace(":", "-").replace(".", "-")[:19]
    output_file = config.output_dir / f"gaia_level{config.level}_{config.mode}_{timestamp}.json"
    markdown_file = config.output_dir / f"gaia_level{config.level}_{config.mode}_{timestamp}.md"

    save_results(results, output_file)
    save_markdown_report(results, markdown_file)

    if config.verbose:
        print(f"\nResults saved to:")
        print(f"  JSON: {output_file}")
        print(f"  Report: {markdown_file}")

    return results
