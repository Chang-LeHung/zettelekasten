"""Launch the storage foundation and unchanged frontend."""

import typer
import uvicorn

from .config import settings
from .infra.database import init_db
from .infra.log import configure_logging, get_logger, uvicorn_log_config

app = typer.Typer(help="Zett")
logger = get_logger(__name__)


@app.callback()
def initialize() -> None:
    configure_logging()


@app.command()
def start(
    host: str = typer.Option(settings.host, "--host", help="Bind address"),
    port: int = typer.Option(settings.port, "--port", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Reload on source changes"),
) -> None:
    """Serve the storage foundation and existing frontend."""
    init_db()
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    logger.info("Starting Zett service; host=%s port=%d reload=%s", host, port, reload)
    typer.echo(f"http://{display_host}:{port}")
    uvicorn.run("zett.main:app", host=host, port=port, reload=reload, log_config=uvicorn_log_config())


if __name__ == "__main__":
    app()
