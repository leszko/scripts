#!/usr/bin/env python3
"""EZVIZ gate control API server."""

import hashlib
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException

load_dotenv(Path(__file__).parent / ".env")

API_BASE = "https://apiieu.ezvizlife.com"
FEATURE_CODE = "92c579faa0902cbfcfcc4fc004ef67e0"

EZVIZ_USERNAME = os.environ["EZVIZ_USERNAME"]
EZVIZ_PASSWORD = os.environ["EZVIZ_PASSWORD"]
EZVIZ_DEVICE_SERIAL = os.environ["EZVIZ_DEVICE_SERIAL"]
API_TOKEN = os.environ["API_TOKEN"]

app = FastAPI(title="EZVIZ Gate Control")

# Cached EZVIZ session
_session: dict = {"session_id": None, "user_id": None, "expires_at": 0}


def _ezviz_login() -> tuple[str, str]:
    """Login to EZVIZ v3 API, returns (session_id, user_id). Caches result."""
    if _session["session_id"] and time.time() < _session["expires_at"]:
        return _session["session_id"], _session["user_id"]

    pwd_hash = hashlib.md5(EZVIZ_PASSWORD.encode()).hexdigest()
    resp = requests.post(
        f"{API_BASE}/v3/users/login/v5",
        data={"account": EZVIZ_USERNAME, "password": pwd_hash, "featureCode": FEATURE_CODE},
        headers={"clientType": "1"},
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()

    _session["session_id"] = body["loginSession"]["sessionId"]
    _session["user_id"] = body["loginUser"]["userId"]
    _session["expires_at"] = time.time() + 3600  # cache for 1 hour

    return _session["session_id"], _session["user_id"]


def _verify_token(authorization: str) -> None:
    if not authorization.startswith("Bearer ") or authorization[7:] != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


def _unlock(lock_no: int, label: str, session_id: str, user_id: str) -> dict:
    """Send unlock request. Retries once with a fresh session on failure."""
    for attempt in range(2):
        resp = requests.put(
            f"{API_BASE}/v3/iot-feature/action/{EZVIZ_DEVICE_SERIAL}/Video/1/DoorLockMgr/RemoteUnlockReq",
            headers={"sessionId": session_id, "Content-Type": "application/json"},
            json={
                "unLockInfo": {
                    "bindCode": f"{FEATURE_CODE}{user_id}",
                    "lockNo": lock_no,
                    "streamToken": "",
                    "userName": user_id,
                }
            },
            timeout=10,
        )
        resp.raise_for_status()
        meta = resp.json().get("meta", {})

        if meta.get("code") == 200:
            return {"status": "ok", "message": f"{label} opened"}

        if attempt == 0:
            _session["expires_at"] = 0
            session_id, user_id = _ezviz_login()

    raise HTTPException(status_code=502, detail=f"EZVIZ error: {meta.get('message')}")


@app.post("/gate/open")
def gate_open(authorization: str = Header()):
    _verify_token(authorization)
    session_id, user_id = _ezviz_login()
    return _unlock(1, "Gate", session_id, user_id)


@app.post("/garden-gate/open")
def garden_gate_open(authorization: str = Header()):
    _verify_token(authorization)
    session_id, user_id = _ezviz_login()
    return _unlock(2, "Garden gate", session_id, user_id)
