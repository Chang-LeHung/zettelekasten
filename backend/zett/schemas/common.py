"""Shared JSON-compatible type aliases."""

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
