"""espsoup-radio — minimal standalone raw-IQ capture backend for the ESPsoup frontend.

Replaces the SignalDeck dependency entirely: opens SoapySDR directly, serves
``/ws/iq`` (capture) and ``/api/health``. No scanner, no database, no auth — one
device, one capture path.

Why standalone (the SignalDeck overlay was ~90% dead weight):
  * We only used SignalDeck's ``SDRDevice`` (~100-line SoapySDR wrapper) and ``/ws/iq``.
  * Its scanner / spectrum / database / auth all touch the device and add contention
    — one of the things that contributed to the RX stall we hit.
  * A single-purpose backend means fewer components touching the SDR → fewer races.

Run:  python -m uvicorn app:app --host 0.0.0.0 --port 8080   (or `python app.py`)
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from contextlib import asynccontextmanager

import numpy as np
import SoapySDR
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger("espsoup-radio")

# The PZSDR clone's RX gain table is inverted above ~10 dB; 10 dB is the top of
# the stable range and beats the (too-weak) 0 dB default we measured.
DEFAULT_GAIN_DB = 10.0
MAX_GAIN_DB = 10.0
OFFSET_LO_HZ = 0.0          # zero-IF: espsoup assumes LO == centre frequency
_SETTLE_S = 0.05
_DISCARD_BLOCKS = 2
_READ_TIMEOUT_S = 5.0

_RX = SoapySDR.SOAPY_SDR_RX
_CF32 = SoapySDR.SOAPY_SDR_CF32


class RadioDevice:
    """Thin SoapySDR receive wrapper (the ~100 lines SignalDeck used to contribute)."""

    def __init__(self, driver: str = "plutosdr", **kwargs) -> None:
        self._dev = SoapySDR.Device(dict(driver=driver, **kwargs))
        self._stream = None
        self._sample_rate = 2_000_000

    def set_sample_rate(self, rate: float) -> None:
        self._dev.setSampleRate(_RX, 0, rate)
        self._sample_rate = rate

    def set_gain_mode(self, manual: bool = True) -> None:
        # SoapySDR setGainMode(direction, channel, automatic): True=AGC, False=manual. Invert.
        self._dev.setGainMode(_RX, 0, not manual)

    def set_gain(self, gain_db: float) -> None:
        self._dev.setGain(_RX, 0, gain_db)

    def set_bandwidth(self, bandwidth_hz: float) -> None:
        self._dev.setBandwidth(_RX, 0, bandwidth_hz)

    def tune(self, frequency_hz: float) -> None:
        self._dev.setFrequency(_RX, 0, frequency_hz)

    def start_stream(self) -> None:
        if self._stream is None:
            self._stream = self._dev.setupStream(_RX, _CF32)
        self._dev.activateStream(self._stream)

    def stop_stream(self) -> None:
        if self._stream is not None:
            self._dev.deactivateStream(self._stream)

    def read_samples(self, num_samples: int, retries: int = 3):
        for _ in range(max(1, retries)):
            buf = np.zeros(num_samples, dtype=np.complex64)
            status = self._dev.readStream(self._stream, [buf], num_samples)
            ret = getattr(status, "ret", status)
            if isinstance(ret, tuple):
                ret = ret[0]
            if ret >= 0:
                return buf[:ret] if ret < num_samples else buf
            time.sleep(0.01)
        return None

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._dev.deactivateStream(self._stream)
            except Exception:
                pass
            self._dev.closeStream(self._stream)
            self._stream = None


class IqSource:
    def __init__(self) -> None:
        self._device: RadioDevice | None = None
        self._lock = asyncio.Lock()
        self._busy = False

    def attach_device(self, device: RadioDevice) -> None:
        self._device = device

    @property
    def busy(self) -> bool:
        return self._busy

    async def capture(self, freq_hz, sample_rate, samples, gain_db, gain_mode="MANUAL") -> dict:
        if self._device is None:
            return {"ok": False, "message": "no SDR device attached"}

        async with self._lock:
            device = self._device
            self._busy = True
            try:
                gain = min(max(float(gain_db), 0.0), MAX_GAIN_DB)
                manual = str(gain_mode).upper() != "HARDWARE"

                device.set_sample_rate(sample_rate)
                device.set_gain_mode(manual)
                device.set_bandwidth(sample_rate)
                device.set_gain(gain)
                device.tune(freq_hz - OFFSET_LO_HZ)
                device.start_stream()

                await asyncio.sleep(_SETTLE_S)
                for _ in range(_DISCARD_BLOCKS):
                    await asyncio.to_thread(device.read_samples, 1024, 2)

                buf = await asyncio.to_thread(self._read_exact, device, samples, _READ_TIMEOUT_S)
                if buf is None:
                    return {"ok": False, "message": "capture read timed out"}
            except Exception as exc:
                logger.error("capture failed: %s", exc, exc_info=True)
                return {"ok": False, "message": str(exc)}
            finally:
                try:
                    device.stop_stream()
                except Exception:
                    pass
                self._busy = False

        iq = buf - buf.mean()  # strip the LO/DC spur
        interleaved = np.empty(samples * 2, dtype=np.float32)
        interleaved[0::2] = iq.real.astype(np.float32)
        interleaved[1::2] = iq.imag.astype(np.float32)
        return {
            "ok": True,
            "iq_b64": base64.b64encode(interleaved.tobytes()).decode("ascii"),
            "n": int(samples),
            "rate": float(sample_rate),
            "bits": 10,
            "capture_us": round(samples / sample_rate * 1e6),
        }

    @staticmethod
    def _read_exact(device, samples: int, timeout_s: float):
        total = np.zeros(samples, dtype=np.complex64)
        got = 0
        deadline = time.monotonic() + timeout_s
        while got < samples:
            if time.monotonic() > deadline:
                return None
            chunk = device.read_samples(samples - got, retries=2)
            if chunk is None or len(chunk) == 0:
                continue
            total[got : got + len(chunk)] = chunk
            got += len(chunk)
        return total


_source = IqSource()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        device = RadioDevice(driver="plutosdr")
        _source.attach_device(device)
        logger.info("SDR device attached (%s)", "plutosdr")
    except Exception as exc:
        logger.error("no SDR device attached: %s", exc)
    yield


app = FastAPI(title="espsoup-radio", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "device_attached": _source._device is not None}


@app.websocket("/ws/iq")
async def ws_iq(websocket: WebSocket):
    await websocket.accept()
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
                await websocket.send_json({"type": "capture", "id": req_id, "ok": False, "message": "bad request"})
                continue

            result = await _source.capture(freq_hz, sample_rate, samples, gain_db, gain_mode)
            result["type"] = "capture"
            result["id"] = req_id
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
