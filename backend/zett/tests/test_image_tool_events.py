"""Multimodal tool output must remain serializable on the SSE boundary."""

import asyncio
import json

from fastapi.testclient import TestClient
from zett_agent import ImageBytesSource, ImageContent, TextContent, ToolMessage

from zett.agent.dispatcher import _message, encode_sse
from zett.infra.agent.runtime import get_agent_runtime_storage
from zett.main import app


def test_image_tool_output_is_encoded_as_data_url():
    message = ToolMessage(
        tool_call_id="image",
        name="view_image",
        content=[ImageContent(source=ImageBytesSource(data=b"image", media_type="image/png"))],
    )
    frame = encode_sse("tool", _message(message))
    payload = json.loads(frame.split("data: ", 1)[1])
    assert payload["output"][0]["url"] == "data:image/png;base64,aW1hZ2U="
    assert payload["tool_call_id"] == "image"


def test_image_tool_history_preserves_order_and_text_on_both_endpoints():
    # Exercise the actual isolated SQLite log and HTTP projection: SSE alone
    # does not catch passing image blocks into the history API's string field.
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        message = ToolMessage(
            tool_call_id="image",
            name="view_image",
            content=[
                TextContent(text="before"),
                ImageContent(
                    source=ImageBytesSource(data=b"image", media_type="image/png"),
                    alt_text="preview.png",
                ),
                TextContent(text="after"),
            ],
        )
        asyncio.run(get_agent_runtime_storage().append(session_id, "request", message))
        detail = client.get(f"/api/agent/sessions/{session_id}")
        history = client.get(f"/api/agent/sessions/{session_id}/messages")
        assert detail.status_code == history.status_code == 200
        restored = detail.json()["messages"][0]
        assert restored == history.json()[0]
        assert restored["content"] == message.text
        assert restored["parts"] == [
            {"type": "text", "text": "before"},
            {
                "type": "image",
                "name": "preview.png",
                "mime_type": "image/png",
                "content_url": "data:image/png;base64,aW1hZ2U=",
            },
            {"type": "text", "text": "after"},
        ]
