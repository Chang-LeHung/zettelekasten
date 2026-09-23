"""Tencent iLink QR login for personal WeChat bots."""

from typing import Any

import httpx

from ..models import LoginCredentials, LoginHandshake, LoginState, LoginStatus

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (4 << 8) | 9)
ILINK_BOT_TYPE = "3"


def _build_headers(*, token: str | None = None, json_content: bool = False) -> dict[str, str]:
    headers = {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
    }
    if json_content:
        headers["Content-Type"] = "application/json"
    if token:
        headers["AuthorizationType"] = "ilink_bot_token"
        headers["Authorization"] = f"Bearer {token}"
    return headers


class WeChatAuthClient:
    """Implement the official iLink QR-code login protocol."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 40.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        """Close the HTTP client when this adapter created it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def create_login(self) -> LoginHandshake:
        """Request one QR code and return the handshake the caller must store."""
        response = await self._get_client().post(
            f"{ILINK_BASE_URL}/ilink/bot/get_bot_qrcode",
            params={"bot_type": ILINK_BOT_TYPE},
            json={"local_token_list": []},
            headers=_build_headers(json_content=True),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("WeChat QR login returned an invalid response")
        qrcode = payload.get("qrcode")
        qr_content = payload.get("qrcode_img_content")
        if not isinstance(qrcode, str) or not qrcode:
            raise ValueError("WeChat QR login response is missing qrcode")
        if not isinstance(qr_content, str) or not qr_content:
            raise ValueError("WeChat QR login response is missing qrcode_img_content")
        return LoginHandshake(
            qr_content=qr_content,
            qr_url=qr_content if qr_content.startswith(("http://", "https://")) else None,
            state={"qrcode": qrcode, "base_url": ILINK_BASE_URL},
        )

    async def poll_login(
        self,
        handshake: LoginHandshake,
        *,
        verify_code: str | None = None,
    ) -> LoginState:
        """Poll one stored handshake and normalize the platform status."""
        qrcode = handshake.state.get("qrcode")
        base_url = handshake.state.get("base_url") or ILINK_BASE_URL
        if not isinstance(qrcode, str) or not qrcode or not isinstance(base_url, str):
            return LoginState(status=LoginStatus.EXPIRED, message="Login session expired; request a new QR code.")
        params: dict[str, str] = {"qrcode": qrcode}
        if verify_code:
            params["verify_code"] = verify_code
        try:
            response = await self._get_client().get(
                f"{base_url.rstrip('/')}/ilink/bot/get_qrcode_status",
                params=params,
                headers=_build_headers(),
            )
            response.raise_for_status()
            payload: Any = response.json()
        except httpx.TimeoutException, httpx.NetworkError:
            return LoginState(status=LoginStatus.PENDING, message="Waiting for the WeChat QR code to be scanned.")
        except httpx.HTTPError as error:
            return LoginState(
                status=LoginStatus.PENDING,
                message=f"WeChat login service is temporarily unavailable: {error}",
            )
        if not isinstance(payload, dict):
            raise ValueError("WeChat QR status returned an invalid response")
        status = payload.get("status")
        if status == "confirmed":
            token = payload.get("bot_token")
            if not isinstance(token, str) or not token:
                raise ValueError("WeChat login confirmed without bot_token")
            config: dict[str, Any] = {"base_url": base_url}
            if isinstance(payload.get("ilink_bot_id"), str):
                config["ilink_bot_id"] = payload["ilink_bot_id"]
            if isinstance(payload.get("ilink_user_id"), str):
                config["ilink_user_id"] = payload["ilink_user_id"]
            return LoginState(
                status=LoginStatus.CONNECTED,
                message="WeChat bot connected.",
                credentials=LoginCredentials(config=config, secrets={"bot_token": token}),
            )
        if status in {"scaned", "scaned_but_redirect"}:
            return LoginState(status=LoginStatus.SCANNED, message="QR code scanned; confirm in WeChat.")
        if status == "need_verifycode":
            return LoginState(status=LoginStatus.VERIFY_REQUIRED, message="Enter the pairing code shown in WeChat.")
        if status in {"expired", "verify_code_blocked"}:
            return LoginState(status=LoginStatus.EXPIRED, message="QR code expired; request a new one.")
        if status == "binded_redirect":
            return LoginState(status=LoginStatus.CONNECTED, message="This WeChat bot is already linked.")
        return LoginState(status=LoginStatus.PENDING, message="Scan the QR code with WeChat to finish signing in.")

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
        return self._client


__all__ = [
    "ILINK_APP_CLIENT_VERSION",
    "ILINK_APP_ID",
    "ILINK_BASE_URL",
    "WeChatAuthClient",
]
