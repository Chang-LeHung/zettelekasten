"""Download, decrypt, and type the media items of one iLink update.

Media arrives as a CDN reference plus an AES-128 key. The wire format and the
decryption rules follow Tencent's ``openclaw-weixin`` channel plugin: fields are
read from ``media`` (``encrypt_query_param``, ``aes_key``, ``full_url``), images
may carry a hex ``aeskey`` instead, and the fetched payload is AES-128-ECB with
PKCS#7 padding.
"""

import base64
import binascii
from dataclasses import dataclass
from mimetypes import guess_type
from typing import Any
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..errors import MediaTooLargeError
from ..log import get_logger
from ..models import MAX_MEDIA_BYTES, MAX_MEDIA_ITEMS, InboundMedia, MediaKind

logger = get_logger(__name__)

#: Where the iLink API serves encrypted media from.
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"

#: How long one CDN download may take before the item is skipped.
MEDIA_DOWNLOAD_TIMEOUT_SECONDS = 60.0

_AES_BLOCK_BYTES = 16

#: iLink item types that carry a download reference.
_IMAGE_ITEM = 2
_VOICE_ITEM = 3
_FILE_ITEM = 4
_VIDEO_ITEM = 5

#: Item type to the kind and payload field that carry its CDN reference.
_MEDIA_ITEM_FIELDS = {
    _IMAGE_ITEM: (MediaKind.IMAGE, "image_item"),
    _VOICE_ITEM: (MediaKind.VOICE, "voice_item"),
    _FILE_ITEM: (MediaKind.FILE, "file_item"),
    _VIDEO_ITEM: (MediaKind.VIDEO, "video_item"),
}

_DEFAULT_MEDIA_TYPES = {
    MediaKind.IMAGE: "image/jpeg",
    MediaKind.VOICE: "audio/silk",
    MediaKind.FILE: "application/octet-stream",
    MediaKind.VIDEO: "video/mp4",
}

#: Voice encodings named by iLink, keyed by ``voice_item.encode_type``.
_VOICE_MEDIA_TYPES = {
    1: "audio/pcm",
    2: "audio/adpcm",
    3: "audio/feature",
    4: "audio/speex",
    5: "audio/amr",
    6: "audio/silk",
    7: "audio/mpeg",
    8: "audio/ogg",
}

#: Leading bytes of the image formats iLink forwards.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)


@dataclass(frozen=True, slots=True)
class MediaRef:
    """One CDN reference found in an inbound message item."""

    kind: MediaKind
    #: MIME type known before the download, refined from the bytes when possible.
    media_type: str
    encrypt_query_param: str | None = None
    full_url: str | None = None
    aes_key: str | None = None
    name: str | None = None


def _media_ref(item: dict[str, Any], *, kind: MediaKind, field: str) -> MediaRef | None:
    """Read one item's media reference, or ``None`` when nothing is downloadable."""
    payload = item.get(field)
    if not isinstance(payload, dict):
        return None
    media = payload.get("media")
    if not isinstance(media, dict):
        return None
    encrypted = media.get("encrypt_query_param")
    full_url = media.get("full_url")
    if not isinstance(encrypted, str) or not encrypted:
        encrypted = None
    if not isinstance(full_url, str) or not full_url:
        full_url = None
    if encrypted is None and full_url is None:
        return None
    aes_key = media.get("aes_key")
    aes_key = aes_key if isinstance(aes_key, str) and aes_key else None
    if kind is MediaKind.IMAGE:
        # Images may publish the key as hex on the item itself; that form wins.
        hex_key = payload.get("aeskey")
        if isinstance(hex_key, str) and hex_key:
            try:
                aes_key = base64.b64encode(bytes.fromhex(hex_key)).decode("ascii")
            except ValueError:
                logger.warning("WeChat image item carries an invalid hex aeskey; ignoring it")
    return MediaRef(
        kind=kind,
        media_type=_declared_media_type(item, kind=kind, field=field),
        encrypt_query_param=encrypted,
        full_url=full_url,
        aes_key=aes_key,
        name=_item_name(item, field=field),
    )


def _declared_media_type(item: dict[str, Any], *, kind: MediaKind, field: str) -> str:
    """Name the MIME type from the item's own metadata, before any bytes exist."""
    payload = item.get(field)
    if not isinstance(payload, dict):
        return _DEFAULT_MEDIA_TYPES[kind]
    if kind is MediaKind.VOICE:
        encode_type = payload.get("encode_type")
        if isinstance(encode_type, int):
            named = _VOICE_MEDIA_TYPES.get(encode_type)
            if named is not None:
                return named
    if kind is MediaKind.FILE:
        guessed, _ = guess_type(str(payload.get("file_name") or ""))
        if guessed:
            return guessed
    return _DEFAULT_MEDIA_TYPES[kind]


def _item_name(item: dict[str, Any], *, field: str) -> str | None:
    """Return the sender-visible file name when the item carries one."""
    payload = item.get(field)
    if not isinstance(payload, dict):
        return None
    name = payload.get("file_name")
    return name if isinstance(name, str) and name else None


def media_refs(message: dict[str, Any], *, limit: int = MAX_MEDIA_ITEMS) -> list[MediaRef]:
    """Return the downloadable media references of one raw iLink update.

    The list stops at ``limit``: an update is untrusted input, and downloading
    every reference an oversized payload names would cost memory the receiver
    never agreed to hold.
    """
    refs: list[MediaRef] = []
    for item in message.get("item_list") or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        fields = _MEDIA_ITEM_FIELDS.get(item_type) if isinstance(item_type, int) else None
        ref = _media_ref(item, kind=fields[0], field=fields[1]) if fields is not None else None
        if ref is not None:
            refs.append(ref)
            if len(refs) >= limit:
                logger.warning("WeChat update names more than %d attachments; ignoring the rest", limit)
                break
    return refs


def build_cdn_download_url(encrypt_query_param: str, cdn_base_url: str) -> str:
    """Build the CDN download URL used when the server sent no ``full_url``."""
    return f"{cdn_base_url.rstrip('/')}/download?encrypted_query_param={quote(encrypt_query_param, safe='')}"


def parse_aes_key(aes_key_base64: str) -> bytes:
    """Decode a wire ``aes_key`` into its raw 16 bytes.

    Images publish ``base64(raw 16 bytes)``; files, voice, and video publish
    ``base64(hex string of 16 bytes)``. Both encodings are accepted.
    """
    try:
        decoded = base64.b64decode(aes_key_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("WeChat media aes_key is not valid base64") from error
    if len(decoded) == _AES_BLOCK_BYTES:
        return decoded
    if len(decoded) == 2 * _AES_BLOCK_BYTES:
        try:
            return bytes.fromhex(decoded.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("WeChat media aes_key is neither 16 raw bytes nor 32 hex characters") from error
    raise ValueError(f"WeChat media aes_key decodes to {len(decoded)} bytes instead of 16")


def decrypt_aes_ecb(ciphertext: bytes, key: bytes) -> bytes:
    """Decrypt one AES-128-ECB payload and drop its PKCS#7 padding when present."""
    if len(key) != _AES_BLOCK_BYTES:
        raise ValueError("WeChat media AES key must be 16 bytes")
    if not ciphertext or len(ciphertext) % _AES_BLOCK_BYTES:
        raise ValueError("WeChat media payload is not a whole number of AES blocks")
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return _strip_pkcs7(plaintext)


def _strip_pkcs7(plaintext: bytes) -> bytes:
    """Remove PKCS#7 padding, tolerating payloads that were never padded."""
    padding = plaintext[-1]
    if 1 <= padding <= _AES_BLOCK_BYTES and plaintext[-padding:] == bytes([padding]) * padding:
        return plaintext[:-padding]
    return plaintext


def _image_media_type(data: bytes, fallback: str) -> str:
    """Prefer the image format the bytes actually are."""
    for signature, media_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback


async def fetch_media(
    client: httpx.AsyncClient,
    ref: MediaRef,
    *,
    cdn_base_url: str = CDN_BASE_URL,
    max_bytes: int = MAX_MEDIA_BYTES,
) -> InboundMedia:
    """Download, decrypt, and describe one referenced attachment.

    Raises:
        MediaTooLargeError: when the payload declares or delivers more than
            ``max_bytes``.
        ValueError: when the reference carries no download URL or cannot be
            decrypted with its declared key.
        httpx.HTTPError: when the CDN request itself fails.
    """
    if ref.full_url:
        url = ref.full_url
    elif ref.encrypt_query_param:
        url = build_cdn_download_url(ref.encrypt_query_param, cdn_base_url)
    else:
        raise ValueError("WeChat media reference has neither full_url nor encrypt_query_param")
    payload = await _download(client, url, max_bytes=max_bytes)
    if ref.aes_key:
        payload = decrypt_aes_ecb(payload, parse_aes_key(ref.aes_key))
    if not payload:
        raise ValueError("WeChat media payload is empty")
    media_type = _image_media_type(payload, ref.media_type) if ref.kind is MediaKind.IMAGE else ref.media_type
    return InboundMedia(kind=ref.kind, media_type=media_type, name=ref.name, data=payload)


async def _download(client: httpx.AsyncClient, url: str, *, max_bytes: int) -> bytes:
    """Read one CDN object, refusing to hold more than ``max_bytes`` of it.

    The body is streamed, so a server that ignores the size contract cannot make
    this process buffer an unbounded payload before the check runs.
    """
    async with client.stream("GET", url, timeout=MEDIA_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as response:
        response.raise_for_status()
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > max_bytes:
            raise MediaTooLargeError(f"WeChat media payload declares {declared} bytes, over the {max_bytes} byte limit")
        payload = bytearray()
        async for chunk in response.aiter_bytes():
            payload.extend(chunk)
            if len(payload) > max_bytes:
                raise MediaTooLargeError(f"WeChat media payload exceeds the {max_bytes} byte limit")
        return bytes(payload)


__all__ = [
    "CDN_BASE_URL",
    "MEDIA_DOWNLOAD_TIMEOUT_SECONDS",
    "MediaRef",
    "build_cdn_download_url",
    "decrypt_aes_ecb",
    "fetch_media",
    "media_refs",
    "parse_aes_key",
]
