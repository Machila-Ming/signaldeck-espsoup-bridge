"""Smoke-test the /ws/iq WebSocket endpoint against the running server."""
import asyncio
import base64
import json

import numpy as np

try:
    import websockets
except ImportError:
    websockets = None


async def main() -> None:
    uri = "ws://127.0.0.1:8080/ws/iq"
    async with websockets.connect(uri, max_size=64 * 1024 * 1024) as ws:
        # ping/pong first
        await ws.send(json.dumps({"type": "ping", "id": 0}))
        pong = json.loads(await ws.recv())
        print("ping ->", pong.get("type"))

        req = {
            "type": "capture",
            "id": 1,
            "freq_hz": 2402_000_000.0,
            "sample_rate": 8_000_000.0,
            "samples": 16380,
            "gain_db": 0.0,
            "gain_mode": "MANUAL",
        }
        await ws.send(json.dumps(req))
        resp = json.loads(await ws.recv())
        print("capture ok =", resp.get("ok"), "n =", resp.get("n"),
              "rate =", resp.get("rate"), "bits =", resp.get("bits"),
              "capture_us =", resp.get("capture_us"))
        if resp.get("ok"):
            raw = base64.b64decode(resp["iq_b64"])
            a = np.frombuffer(raw, dtype=np.float32)
            c = a[0::2] + 1j * a[1::2]
            print("iq floats:", a.shape, "complex n:", c.shape,
                  "peak=", round(float(np.max(np.abs(c))), 4),
                  "rms=", round(float(np.sqrt(np.mean(np.abs(c) ** 2))), 4),
                  "dc_after_mean=", round(float(np.abs(c.mean())), 6))
        else:
            print("message:", resp.get("message"))


asyncio.run(main())
