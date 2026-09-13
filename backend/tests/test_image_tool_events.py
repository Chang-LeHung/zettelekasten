"""Multimodal tool output must remain serializable on the SSE boundary."""

import json

from zett_agent import ImageBytesSource, ImageContent, ToolMessage

from zett.agent.dispatcher import _message, encode_sse


def test_image_tool_output_is_encoded_as_data_url():
    message = ToolMessage(
        tool_call_id="image",
        name="read_image",
        content=[ImageContent(source=ImageBytesSource(data=b"image", media_type="image/png"))],
    )
    frame = encode_sse("tool", _message(message))
    payload = json.loads(frame.split("data: ", 1)[1])
    assert payload["output"][0]["url"] == "data:image/png;base64,aW1hZ2U="
    assert payload["tool_call_id"] == "image"
