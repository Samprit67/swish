"""``swish`` — the command line.

    swish value "Luka Doncic"      # trade-value breakdown for one player
    swish serve                    # start the web dashboard
    swish version
"""

from __future__ import annotations

import typer

from swish import __version__

app = typer.Typer(
    add_completion=False,
    help="Estimate an NBA player's trade value from his stats and contract.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(f"swish {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
