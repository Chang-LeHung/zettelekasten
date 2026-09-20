"""Invariant tests for relative object keys and local path containment."""

import pytest
from fastapi.testclient import TestClient

from zett.application.object_store import ObjectKey
from zett.infra.object_store import LocalObjectStore
from zett.main import app


@pytest.mark.parametrize(
    "key",
    ["", "/absolute", "../escape", "assets/../escape", "assets//file", "assets\\file", " assets/file "],
)
def test_object_keys_reject_absolute_parent_and_non_posix_paths(key: str) -> None:
    with pytest.raises(ValueError):
        ObjectKey(key)


async def test_local_object_store_writes_and_addresses_one_relative_key(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)
    key = ObjectKey("assets/static/example.txt")

    stored = await store.write(key, b"object")

    assert stored.key == key
    assert stored.size_bytes == 6
    assert await store.read(key) == b"object"
    assert store.url(key) == "/api/files/assets/static/example.txt"
    assert store.resolve(key) == tmp_path / "assets" / "static" / "example.txt"
    assert await store.delete(key) is True
    assert await store.exists(key) is False


async def test_local_object_store_deletes_a_whole_tree_and_prunes_its_parents(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)
    session_directory = ObjectKey("assets/sessions/session-1")
    await store.write("assets/sessions/session-1/uploads/first.png", b"first")
    await store.write("assets/sessions/session-1/uploads/second.png", b"second")
    await store.write("assets/sessions/session-1/asset-1.pdf", b"asset")
    await store.write("assets/sessions/session-2/uploads/kept.png", b"kept")

    assert await store.delete_tree(session_directory) == 3

    assert not store.resolve(session_directory).exists()
    assert await store.exists("assets/sessions/session-2/uploads/kept.png")
    # An absent directory is a no-op so session cleanup can stay unconditional.
    assert await store.delete_tree(session_directory) == 0


def test_local_object_store_rejects_symlink_escape(tmp_path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    store = LocalObjectStore(root)

    with pytest.raises(ValueError, match="escapes storage_root"):
        store.resolve("linked/file.txt")


def test_file_endpoint_does_not_expose_private_storage_root_files(tmp_path) -> None:
    (tmp_path / "zett.db").write_bytes(b"private")

    with TestClient(app) as client:
        assert client.get("/api/files/zett.db").status_code == 404
