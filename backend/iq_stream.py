"""Raw-IQ capture WebSocket endpoint for the ESPsoup frontend.

Request/response over ``/ws/iq``::

    -> {"type": "capture", "id": 1, "freq_hz": 2402000000.0,
        "sample_rate": 8000000.0, "samples": 16380, "bits": 10,
        "gain_db": 0.0, "gain_mode": "MANUAL"}
    <- {"type": "capture", "id": 1, "ok": true, "iq_b64": "...",
        "n": 16380, "rate": 8000000.0, "bits": 10, "capture_us": 123...}

``iq_b64`` is the interleaved little-endian float32 I/Q array, base64-encoded.
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from signaldeck.api.websocket._auth import ws_authorized
from signaldeck.engine.iq_source import DEFAULT_GAIN_DB, get_iq_source

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/iq")
async def ws_iq(websocket: WebSocket):
    if not await ws_authorized(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    source = get_iq_source()
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if data.get("type") != "capture":
                continue

            req_id = data.get("id")
            try:
                freq_hz = float(data.get("freq_hz", 0.0))
                sample_rate = float(data.get("sample_rate", 8_000_000.0))
                samples = int(data.get("samples", 16380))
                gain_db = float(data.get("gain_db", DEFAULT_GAIN_DB))
                gain_mode = str(data.get("gain_mode", "MANUAL"))
            except (TypeError, ValueError):
                await websocket.send_json(
                    {"type": "capture", "id": req_id, "ok": False, "message": "bad request"}
                )
                continue

            result = await source.capture(freq_hz, sample_rate, samples, gain_db, gain_mode)
            result["type"] = "capture"
            result["id"] = req_id
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass
