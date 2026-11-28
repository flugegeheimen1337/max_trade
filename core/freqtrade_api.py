"""Call the local Freqtrade API. Credentials stay in the request."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from base64 import b64encode


class ApiError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


def post_command(base_url: str, username: str, password: str, command: str) -> str:
    token = _login(base_url, username, password)
    url = base_url.rstrip("/") + f"/api/v1/{command}"
    request = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    return _read(request)


def _login(base_url: str, username: str, password: str) -> str:
    token_bytes = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/v1/token/login",
        data=b"",
        method="POST",
        headers={"Authorization": f"Basic {token_bytes}", "Accept": "application/json"},
    )
    payload = json.loads(_read(request))
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ApiError("Freqtrade login did not return an access token.")
    return access_token


def _read(request: urllib.request.Request) -> str:
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise ApiError(f"Freqtrade API returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ApiError("Freqtrade API is not reachable. Start it with lab up.") from exc
