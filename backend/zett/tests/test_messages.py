"""Validation rules of the FrontUserMessage <-> UserMessage codec."""

import base64

import pytest
from pydantic import ValidationError
from zett_agent.messages import (
    ImageBytesSource,
    ImageContent,
    ImageUrlSource,
    TextContent,
    UserMessage,
)

from zett.messages import (
    FrontImagePart,
    FrontTextPart,
    FrontUserMessage,
    InvalidImagePayloadError,
    MessageImageCountExceeded,
    MessageImageSizeExceeded,
    MessagePartBytesError,
    MessagePartCodec,
    UnsupportedMessagePartError,
)

PNG_BASE64 = base64.b64encode(b"png-bytes").decode("ascii")
DATA_URL = f"data:image/png;base64,{PNG_BASE64}"


def image(content_url: str = DATA_URL, name: str = "shot.png") -> FrontImagePart:
    return FrontImagePart(name=name, mime_type="image/png", content_url=content_url)


def front(*parts: object) -> FrontUserMessage:
    return FrontUserMessage.model_validate({"raw_content": "", "parts": list(parts)})


def test_ingest_keeps_order_and_keeps_base64_untouched() -> None:
    message = MessagePartCodec(max_images=2, max_bytes=1_024).to_user_message(
        front(FrontTextPart(text="before"), image(), FrontTextPart(text="after"))
    )

    assert message.content == [
        TextContent("before"),
        ImageContent(source=ImageUrlSource(DATA_URL), alt_text="shot.png"),
        TextContent("after"),
    ]


def test_ingest_falls_back_to_raw_content_without_parts() -> None:
    codec = MessagePartCodec()

    assert codec.to_user_message(FrontUserMessage(raw_content="/zett-review check this")).content == (
        "/zett-review check this"
    )
    assert codec.to_user_message(front(FrontTextPart(text="typed"))).content == [TextContent("typed")]


def test_front_models_reject_bytes_instead_of_decoding_them() -> None:
    with pytest.raises(ValidationError):
        FrontImagePart(name="shot.png", mime_type="image/png", content_url=b"png-bytes")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        FrontTextPart(text=b"typed")  # type: ignore[arg-type]


def test_ingest_rejects_raw_bytes_that_bypass_the_models() -> None:
    codec = MessagePartCodec()
    bytes_image = FrontImagePart.model_construct(
        type="image",
        name="shot.png",
        mime_type="image/png",
        content_url=b"png-bytes",
    )
    bytes_text = FrontTextPart.model_construct(type="text", text=b"typed")

    with pytest.raises(MessagePartBytesError, match="base64 text, not raw bytes"):
        codec.to_user_message(front(bytes_image))
    with pytest.raises(MessagePartBytesError, match="not raw bytes"):
        codec.to_user_message(front(bytes_text))


@pytest.mark.parametrize(
    "content_url",
    [
        "data:image/png;base64,%%%",
        "data:image/png;base64,abc",
        "data:image/png;base64,",
        "data:image/png,notbase64",
        "not-a-url",
    ],
)
def test_ingest_rejects_invalid_image_urls(content_url: str) -> None:
    part = FrontImagePart.model_construct(
        type="image",
        name="shot.png",
        mime_type=None,
        content_url=content_url,
    )

    with pytest.raises(InvalidImagePayloadError):
        MessagePartCodec().to_user_message(front(part))


def test_ingest_rejects_a_mime_type_that_contradicts_the_data_url() -> None:
    part = FrontImagePart(name="shot.png", mime_type="image/jpeg", content_url=DATA_URL)

    with pytest.raises(InvalidImagePayloadError, match="declares image/jpeg"):
        MessagePartCodec().to_user_message(front(part))


def test_ingest_accepts_remote_image_urls_without_a_byte_budget() -> None:
    part = FrontImagePart(name="chart.png", content_url="https://example.com/chart.png")

    message = MessagePartCodec(max_bytes=1).to_user_message(front(part))

    assert message.content == [
        ImageContent(source=ImageUrlSource("https://example.com/chart.png"), alt_text="chart.png")
    ]


def test_ingest_rejects_untyped_parts() -> None:
    part = FrontTextPart.model_construct(type="text", text="ok")
    message = FrontUserMessage.model_construct(raw_content="", parts=[part, {"type": "text", "text": "raw"}])

    with pytest.raises(UnsupportedMessagePartError, match="Unsupported message part"):
        MessagePartCodec().to_user_message(message)


def test_ingest_enforces_image_count_and_size_limits() -> None:
    with pytest.raises(MessageImageCountExceeded, match="up to 1 image"):
        MessagePartCodec(max_images=1).to_user_message(front(image(name="a.png"), image(name="b.png")))

    oversized = f"data:image/png;base64,{base64.b64encode(b'12345').decode('ascii')}"
    with pytest.raises(MessageImageSizeExceeded, match="configured limit"):
        MessagePartCodec(max_bytes=4).to_user_message(front(image(oversized, "big.png")))


def test_projection_encodes_stored_bytes_as_data_urls() -> None:
    parts = MessagePartCodec().to_front_parts(
        [
            TextContent("tool output"),
            ImageContent(source=ImageBytesSource(b"png-bytes", "image/png"), alt_text="pg-01.png"),
        ]
    )

    assert parts == [
        FrontTextPart(text="tool output"),
        FrontImagePart(name="pg-01.png", mime_type="image/png", content_url=DATA_URL),
    ]
    assert all(isinstance(part, (FrontTextPart, FrontImagePart)) for part in parts)


def test_projection_keeps_string_content_and_remote_urls() -> None:
    codec = MessagePartCodec()

    assert codec.to_front_parts("plain tool output") == []
    assert codec.to_front_parts(
        [ImageContent(source=ImageUrlSource("https://example.com/a.png"), alt_text="a.png")]
    ) == [FrontImagePart(name="a.png", content_url="https://example.com/a.png")]
    assert codec.to_front_parts([ImageContent(source=ImageUrlSource(DATA_URL), alt_text="shot.png")]) == [
        FrontImagePart(name="shot.png", mime_type="image/png", content_url=DATA_URL)
    ]


def test_projection_round_trips_a_user_message() -> None:
    codec = MessagePartCodec()
    message = UserMessage(content=[TextContent("hello"), ImageContent(source=ImageUrlSource(DATA_URL), alt_text="a")])

    front_message = codec.to_front_message(message)

    assert front_message.raw_content == "hello"
    assert front_message.parts == [
        FrontTextPart(text="hello"),
        FrontImagePart(name="a", mime_type="image/png", content_url=DATA_URL),
    ]
    assert codec.to_user_message(front_message) == message


def test_projection_never_emits_raw_bytes() -> None:
    codec = MessagePartCodec()
    part = codec.to_front_parts(
        [ImageContent(source=ImageBytesSource(b"png-bytes", "image/png"), alt_text="shot.png")]
    )[0]

    dumped = part.model_dump()
    assert all(not isinstance(value, (bytes, bytearray, memoryview)) for value in dumped.values())
    with pytest.raises(MessagePartBytesError, match="must be raw bytes"):
        codec.to_front_parts(
            [
                ImageContent(source=ImageBytesSource("not-bytes", "image/png"))  # type: ignore[arg-type]
            ]
        )
