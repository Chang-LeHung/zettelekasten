"""Chrome-extension-only transport for the application browser bridge."""

import asyncio
import json
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ...agent.browser import MAX_BROWSER_MESSAGE, BrowserReply, BrowserUnavailableError, browser_bridge

router = APIRouter(prefix="/agent", tags=["browser"])


@router.websocket("/{session_id}/browser")
async def browser_socket(socket: WebSocket, session_id: str) -> None:
    """Issue an ephemeral capability only to extension origins, not web pages.

    Origin is a browser isolation check, not remote-user authentication: like the
    rest of this local API, deployments outside loopback need an authenticated
    proxy with WSS. Tokens travel in frames/request bodies, never URL logs.
    """
    if not re.fullmatch(r"chrome-extension://[a-p]{32}", socket.headers.get("origin", "")):
        await socket.close(code=1008)
        return
    await socket.accept()
    connection = None
    send_lock = asyncio.Lock()

    async def send(payload: dict[str, object]) -> None:
        async with send_lock:
            await socket.send_json(payload)

    try:
        connection = await browser_bridge.connect(session_id, send)
        await send({"type": "ready", "token": connection.token})
        while True:
            text = await asyncio.wait_for(socket.receive_text(), timeout=50)
            if len(text.encode("utf-8")) > MAX_BROWSER_MESSAGE:
                await socket.close(code=1009)
                break
            payload = json.loads(text)
            if payload == {"type": "ping"}:
                await send({"type": "pong"})
                continue
            reply = BrowserReply.model_validate(payload)
            connection.resolve(reply)
    except BrowserUnavailableError:
        await socket.close(code=1008)
    except (ValueError, ValidationError, asyncio.TimeoutError):
        await socket.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        if connection is not None:
            browser_bridge.disconnect(connection)
