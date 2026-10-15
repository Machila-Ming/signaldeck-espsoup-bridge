"""On-demand raw-IQ capture source for the ESPsoup web frontend.

ESPsoup's SDR client drives its spectrum view and every host-side decoder
(BLE, Wi-Fi, LoRa, …) through a single ``radio.capture(c)`` call: tune the LO,
read ``samples`` of raw I/Q, and hand an interleaved float32 array back to
JavaScript.  This module is the SignalDeck equivalent: it takes the shared
SoapySDR device for the duration of one capture, then releases the stream so
the scanner / live-spectrum paths can run again.

One capture = tune LO to ``freq`` (zero-IF: espsoup assumes LO == centre), set
sample rate / gain / bandwidth, settle, read N complex samples, strip the LO
feed-through (DC) spur in the time domain, and return interleaved little-endian
float32 I/Q.

Conventions (must match ESPsoup's ``unpackIq`` output exactly):

* I/Q is left in the native SoapySDR sense (I + jQ, +f above the LO) — it is
  **not** Q-negated, because ``unpackIq`` already negates Q and the decoders
  expect that final, standard orientation.
* Amplitude is **not** peak-normalised: SoapySDR CF32 is already ~[-1, 1], so
  ESPsoup's software AGC (clip > 0.98 / rms < 0.03) sees the true ADC scale.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time

import numpy as np

logger = logging.getLogger(__name__)

# Zero-IF: espsoup's spectrum axis and every host-side decoder assume LO == the
# requested centre frequency, so a non-zero offset would shift the whole
# spectrum axis and break BLE/GFSK decoding.  The DC spur from LO feed-through
# is stripped in the time domain (buf - buf.mean()) instead.  The clone's RX
# gain table is inverted above ~10 dB, so the default is 0 dB and anything above
# 10 dB is clamped away.
OFFSET_LO_HZ = 0.0
DEFAULT_GAIN_DB = 0.0
MAX_GAIN_DB = 10.0

# Settle/flush budget (see SpectrumSource): the PlutoSDR IIO ring buffer is
# ~3.3 ms at 20 MS/s and the LO needs ~1 ms + network latency to lock, so a
# short settle reads the previous frequency.  50 ms lets it rotate onto the new
# LO before we read.
_SETTLE_S = 0.05
_DISCARD_BLOCKS = 2
_READ_TIMEOUT_S = 5.0


def _read_exact(device, samples: int, timeout_s: float) -> np.ndarray | None:
    """Read exactly ``samples`` complex samples, accumulating across readStream
    calls (which may return fewer than requested or an empty chunk)."""
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


class IqSource:
    def __init__(self) -> None:
        self._device = None
        self._lock = asyncio.Lock()
        self._busy = False
        self._captures = 0

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def device_attached(self) -> bool:
        return self._device is not None

    def attach_device(self, device) -> None:
        self._device = device

    async def capture(
        self,
        freq_hz: float,
        sample_rate: float,
        samples: int,
        gain_db: float = DEFAULT_GAIN_DB,
        gain_mode: str = "MANUAL",
    ) -> dict:
        """Capture ``samples`` of raw I/Q centred on ``freq_hz``.

        Returns ``{"ok": True, "iq_b64": ..., "n": ..., "rate": ...}`` on
        success or ``{"ok": False, "message": ...}`` on failure.  Captures are
        serialised with an asyncio lock; the scanner main loop checks :attr:`busy`
        so it does not touch the device mid-capture.
        """
        if self._device is None:
            return {"ok": False, "message": "no SDR device attached"}

        # A running live-spectrum source owns the stream; refuse rather than
        # corrupt its continuous read.
        from signaldeck.engine.spectrum_source import get_spectrum_source
        if get_spectrum_source().running:
            return {"ok": False, "message": "live spectrum is running"}

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

                buf = await asyncio.to_thread(_read_exact, device, samples, _READ_TIMEOUT_S)
                if buf is None:
                    return {"ok": False, "message": "capture read timed out"}
            except Exception as exc:
                logger.error("iq capture failed: %s", exc, exc_info=True)
                return {"ok": False, "message": str(exc)}
            finally:
                try:
                    device.stop_stream()
                except Exception:
                    pass
                self._busy = False

        self._captures += 1
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


_iq_source: IqSource | None = None


def get_iq_source() -> IqSource:
    global _iq_source
    if _iq_source is None:
        _iq_source = IqSource()
    return _iq_source
