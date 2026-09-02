import typer

from .application.services import CardApplicationService, TagApplicationService
from .database import init_db
from .schemas import CardCreate, TagCreate

app = typer.Typer(help="Personal knowledge card system")
tag_app = typer.Typer(help="Manage hierarchical tags")
app.add_typer(tag_app, name="tag")


@app.callback()
def initialize() -> None:
    init_db()


@app.command()
def add(
    text: str = typer.Argument(...),
    card_type: str = typer.Option("note", "--type"),
    title: str = typer.Option("", "--title"),
    tag_ids: list[int] = typer.Option([], "--tag-id"),
) -> None:
    payload = CardCreate(type=card_type, title=title or text[:60], content=text, raw_content=text, tag_ids=tag_ids)
    print(CardApplicationService.create(payload)["id"])


@app.command()
def search(query: str, card_type: str = typer.Option(None, "--type"), tag_id: int = typer.Option(None, "--tag-id")) -> None:
    for card in CardApplicationService.search(query, card_type, tag_id):
        print(f"{card['id']} [{card['type']}] {card['title']}")


@app.command()
def show(card_id: str) -> None:
    card = CardApplicationService.get(card_id)
    print(f"# {card['title']}\n\n{card['content']}\n\nTags: {', '.join(tag['path'] for tag in card['tags'])}")


@tag_app.command("add")
def add_tag(name: str, parent_id: int = typer.Option(None, "--parent-id")) -> None:
    print(TagApplicationService.create(TagCreate(name=name, parent_id=parent_id))["path"])


@tag_app.command("tree")
def tag_tree() -> None:
    def print_nodes(nodes: list[dict], prefix: str = "") -> None:
        for index, node in enumerate(nodes):
            last = index == len(nodes) - 1
            print(prefix + ("└── " if last else "├── ") + f"{node['name']} ({node['card_count']})")
            print_nodes(node["children"], prefix + ("    " if last else "│   "))

    print_nodes(TagApplicationService.tree())


if __name__ == "__main__":
    app()
