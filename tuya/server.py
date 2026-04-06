#!/usr/bin/env python3
"""Tuya switch control API server."""

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException

load_dotenv(Path(__file__).parent / ".env")

TUYA_CLIENT_ID = os.environ["TUYA_CLIENT_ID"]
TUYA_CLIENT_SECRET = os.environ["TUYA_CLIENT_SECRET"]
TUYA_DEVICE_ID = os.environ["TUYA_DEVICE_ID"]
TUYA_BASE_URL = os.environ["TUYA_BASE_URL"]
API_TOKEN = os.environ["API_TOKEN"]

app = FastAPI(title="Tuya Switch Control")

_session: dict = {"access_token": None, "expires_at": 0}


def _sign(method: str, url: str, body: str, access_token: str | None = None) -> tuple[str, str]:
    """Compute Tuya API signature. Returns (sign, t)."""
    t = str(int(time.time() * 1000))
    content_hash = hashlib.sha256(body.encode()).hexdigest()
    string_to_sign = f"{method}\n{content_hash}\n\n{url}"
    sign_str = TUYA_CLIENT_ID + (access_token or "") + t + string_to_sign
    sign = hmac.new(
        TUYA_CLIENT_SECRET.encode(), sign_str.encode(), hashlib.sha256
    ).hexdigest().upper()
    return sign, t


def _tuya_token() -> str:
    """Get a Tuya access token, caching it until expiry."""
    if _session["access_token"] and time.time() < _session["expires_at"]:
        return _session["access_token"]

    url = "/v1.0/token?grant_type=1"
    sign, t = _sign("GET", url, "")
    resp = requests.get(
        f"{TUYA_BASE_URL}{url}",
        headers={
            "client_id": TUYA_CLIENT_ID,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data.get("success"):
        raise HTTPException(status_code=502, detail=f"Tuya token error: {data.get('msg')}")

    _session["access_token"] = data["result"]["access_token"]
    _session["expires_at"] = time.time() + data["result"]["expire_time"] - 60
    return _session["access_token"]


def _send_command(value: bool) -> dict:
    """Send switch command. Retries once with a fresh token on failure."""
    for attempt in range(2):
        token = _tuya_token()
        url = f"/v1.0/devices/{TUYA_DEVICE_ID}/commands"
        body = json.dumps({"commands": [{"code": "switch_1", "value": value}]})
        sign, t = _sign("POST", url, body, token)

        resp = requests.post(
            f"{TUYA_BASE_URL}{url}",
            headers={
                "client_id": TUYA_CLIENT_ID,
                "access_token": token,
                "sign": sign,
                "t": t,
                "sign_method": "HMAC-SHA256",
                "Content-Type": "application/json",
            },
            data=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("success"):
            return {"status": "ok", "message": f"Switch turned {'on' if value else 'off'}"}

        if attempt == 0:
            _session["access_token"] = None
            _session["expires_at"] = 0

    raise HTTPException(status_code=502, detail=f"Tuya error: {data.get('msg')}")


def _verify_token(authorization: str) -> None:
    if not authorization.startswith("Bearer ") or authorization[7:] != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/switch/on")
def switch_on(authorization: str = Header()):
    _verify_token(authorization)
    return _send_command(True)


@app.post("/switch/off")
def switch_off(authorization: str = Header()):
    _verify_token(authorization)
    return _send_command(False)
