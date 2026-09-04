from collections.abc import Sequence

import typer
import uvicorn

from .application.services import CardApplicationService, TagApplicationService
from .config import settings
from .infra.database import init_db
from .infra.logging import configure_logging, get_logger, uvicorn_log_config
from .schemas import CardCreate, CardType, TagCreate, TagOut

app = typer.Typer(help="Personal knowledge card system")
tag_app = typer.Typer(help="Manage hierarchical tags")
app.add_typer(tag_app, name="tag")
logger = get_logger(__name__)


@app.callback()
def initialize() -> None:
    configure_logging()
    init_db()


@app.command()
def add(
    text: str = typer.Argument(...),
    card_type: CardType = typer.Option(CardType.NOTE, "--type"),
    title: str = typer.Option("", "--title"),
    tag_ids: list[int] = typer.Option([], "--tag-id"),
) -> None:
    payload = CardCreate(
        type=card_type,
        title=title or text[:60],
        content=text,
        raw_content=text,
        tag_ids=tag_ids,
    )
    print(CardApplicationService.create(payload).id)


@app.command()
def search(
    query: str,
    card_type: str | None = typer.Option(None, "--type"),
    tag_id: int | None = typer.Option(None, "--tag-id"),
) -> None:
    for card in CardApplicationService.search(query, card_type, tag_id):
        print(f"{card.id} [{card.type}] {card.title}")


@app.command()
def show(card_id: str) -> None:
    card = CardApplicationService.get(card_id)
    if card is None:
        raise typer.BadParameter(f"Card not found: {card_id}")
    print(f"# {card.title}\n\n{card.content}\n\nTags: {', '.join(tag.path for tag in card.tags)}")


@app.command()
def start(
    host: str = typer.Option(settings.host, "--host", help="Bind address"),
    port: int = typer.Option(settings.port, "--port", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Reload on source changes"),
) -> None:
    """Start the knowledge card API service."""
    init_db()
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    logger.info("Starting KCS service; host=%s port=%d reload=%s", host, port, reload)
    typer.echo(f"http://{display_host}:{port}")
    uvicorn.run("kcs.main:app", host=host, port=port, reload=reload, log_config=uvicorn_log_config())


@tag_app.command("add")
def add_tag(name: str, parent_id: int | None = typer.Option(None, "--parent-id")) -> None:
    print(TagApplicationService.create(TagCreate(name=name, parent_id=parent_id)).path)


@tag_app.command("tree")
def tag_tree() -> None:
    def print_nodes(nodes: Sequence[TagOut], prefix: str = "") -> None:
        for index, node in enumerate(nodes):
            last = index == len(nodes) - 1
            print(prefix + ("└── " if last else "├── ") + f"{node.name} ({node.card_count})")
            print_nodes(node.children, prefix + ("    " if last else "│   "))

    print_nodes(TagApplicationService.tree())


if __name__ == "__main__":
    app()
