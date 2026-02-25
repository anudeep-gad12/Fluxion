"""CLI entry point.

Usage:
    reasoner [OPTIONS]
    python -m cli [OPTIONS]

Options:
    --api-url       Backend URL (default: http://127.0.0.1:9000)
    --provider      default | chatgpt
    --model         Model name override
    --mode          chat | agent (default: agent)
    --permission    strict | relaxed | yolo (default: strict)
    --working-dir   Working directory for filesystem tools (default: .)
    --max-steps     Maximum agent steps (default: 15)

The CLI always uses the 'coding' profile. Profile selection is web-UI only.
"""

import click


@click.command()
@click.option(
    "--api-url",
    default="http://127.0.0.1:9000",
    help="Backend API URL",
    envvar="REASONER_API_URL",
)
@click.option(
    "--provider",
    default="default",
    type=click.Choice(["default", "chatgpt"]),
    help="LLM provider",
)
@click.option(
    "--model",
    default=None,
    help="Model name override (e.g., o4-mini)",
)
@click.option(
    "--mode",
    default="agent",
    type=click.Choice(["chat", "agent"]),
    help="Chat mode or agent mode with tools",
)
@click.option(
    "--permission",
    default="strict",
    type=click.Choice(["strict", "relaxed", "yolo"]),
    help="Permission policy for tool execution",
)
@click.option(
    "--working-dir",
    default=".",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    help="Working directory for filesystem tools",
)
@click.option(
    "--max-steps",
    default=15,
    type=int,
    help="Maximum agent steps",
)
def main(
    api_url: str,
    provider: str,
    model: str | None,
    mode: str,
    permission: str,
    working_dir: str,
    max_steps: int,
) -> None:
    """Reasoner CLI — terminal coding assistant."""
    from .app import ReasonerApp
    from .config import CLIConfig

    config = CLIConfig.from_args(
        api_url=api_url,
        provider=provider,
        model=model,
        mode=mode,
        permission=permission,
        working_dir=working_dir,
        max_steps=max_steps,
    )

    app = ReasonerApp(config)
    app.run()


if __name__ == "__main__":
    main()
