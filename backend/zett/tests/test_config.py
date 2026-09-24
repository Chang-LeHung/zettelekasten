from pathlib import Path

from zett import config


def test_default_user_data_directory_uses_zett_namespace() -> None:
    assert config.USER_DATA_DIR == Path.home() / ".zettelekasten"
