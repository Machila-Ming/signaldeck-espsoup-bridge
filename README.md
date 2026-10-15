# signaldeck-espsoup-bridge

Drive ESPsoup's **web frontend** — the Spectrum tab and every host-side
decoder (BLE/GFSK, Wi-Fi, nRF, Zigbee, LoRa, LTE cell search, FPV, Remote ID,
camera, radar) — from **SignalDeck's SoapySDR backend** instead of a WebSerial
ESP32-C5.

ESPsoup's ESP32 firmware and frontend are two separate codebases with different
licenses. This bridge is the minimal seam between them:

* **Backend** (runs inside SignalDeck): a `/ws/iq` WebSocket endpoint that, for
  each request, tunes the shared SoapySDR device to a centre frequency, reads N
  samples of raw I/Q, and returns interleaved `float32` over the wire.
* **Frontend** (runs inside ESPsoup's `www/`): a small `SignalDeckRadio`
  adapter class that re-implements the narrow surface ESPsoup actually calls —
  `run()`, `connected`, `name`, `connect/shutdown/disconnect`, the no-op
  `tune/gain/filter/apply`, and `capture()`.

Everything else in ESPsoup stays untouched. Features that need ESP32 firmware
support (the `CAPS` tokens) are simply left *disabled* by an empty capability
set — see "Feature audit" below.

---

## Architecture

```
 ESPsoup www/ (browser)                      SignalDeck (VM, SoapySDR)
 ──────────────────────                      ─────────────────────────
 Spectrum tab ──┐
 BLE/GFSK       ├─► radio.capture(c) ──► SignalDeckRadio ──► /ws/iq ──► IqSource
 Wi-Fi / nRF    │      (host-side          (frontend/            (backend/
 Zigbee / LoRa  │       JS decode)         signaldeck.js)        iq_source.py)
 LTE / FPV / RID│                                                  │
 ...            ┘                                                  ▼
                                                        SoapySDR (plutosdr,
                                                        AD9364, 70MHz–6GHz)
```

One capture = one `/ws/iq` round-trip: tune LO to `freq` (zero-IF, LO ==
centre), set sample rate / gain / bandwidth, settle, read N complex samples,
strip the LO feed-through (DC) spur in the time domain, and return interleaved
little-endian `float32` I/Q.

The shared SoapySDR device is taken for the duration of one capture, then
released, so the scanner / live-spectrum paths keep working in between.
Captures are serialised with an asyncio lock, and `IqSource` refuses to run
while the live-spectrum source owns the stream (and vice-versa).

---

## File manifest

| File | Destination | What it is |
|------|-------------|------------|
| `backend/iq_source.py` | `signaldeck/engine/iq_source.py` | **New module.** `IqSource` + `get_iq_source()`; the capture engine. |
| `backend/iq_stream.py` | `signaldeck/api/websocket/iq_stream.py` | **New module.** `/ws/iq` WebSocket router. |
| `backend/server.py` | `signaldeck/api/server.py` (reference) | **Patched copy** of SignalDeck's `server.py`; shows the 2-line diff that registers `iq_stream`. |
| `backend/main.py` | `signaldeck/main.py` (reference) | **Patched copy** of SignalDeck's `main.py`; shows the ~6-line diff that attaches the device to `IqSource` and guards on `busy`. |
| `frontend/signaldeck.js` | ESPsoup `www/signaldeck.js` | **New file.** `SignalDeckRadio` adapter; sets `window.__SIGNALDECK__`. |
| `tests/test_iq_capture.py` | anywhere | Smoke-test `IqSource` against the live PZSDR (`plutosdr`). |
| `tests/test_ws_iq.py` | anywhere | Smoke-test the `/ws/iq` endpoint against a running server. |

`server.py` and `main.py` are full copies of SignalDeck's own files (GPL-3.0)
with the integration lines applied, included so the exact change is visible
without diffing against the fork. The genuinely new code is `iq_source.py`,
`iq_stream.py`, `signaldeck.js`, and the two tests.

---

## Wiring into SignalDeck

`iq_source.py` and `iq_stream.py` are drop-in additions to a full SignalDeck
checkout:

```bash
cp backend/iq_source.py   <signaldeck>/signaldeck/engine/iq_source.py
cp backend/iq_stream.py   <signaldeck>/signaldeck/api/websocket/iq_stream.py
```

Then apply the two reference diffs:

1. **`server.py`** — import and register the router (see the two lines at the
   `ws_iq_router` / `app.include_router(ws_iq_router)` sites in
   `backend/server.py`).
2. **`main.py`** — import `get_iq_source`, `attach_device(device)` next to the
   existing `get_spectrum_source()` setup, and add `get_iq_source().busy` to the
   guard in the scanner loop (see `backend/main.py`).

### Known dangling reference

`backend/iq_source.py` imports
`from signaldeck.engine.spectrum_source import get_spectrum_source`, and
`backend/main.py` uses `get_spectrum_source()` in the same guard. This module
exists in the **full SignalDeck checkout** the code was written against (the
VM at `~/Workspace/signaldeck`), but is **missing from the public fork**
`Machila-Ming/signaldeck` (last pushed 2026-09-09), which is stale — it is also
missing `api/routes/video.py`, `gfsk.py`, `spectrum.py`, and others.

So: this bridge targets the **VM's SignalDeck tree**, not the public fork. To
run it against the fork you must first restore `signaldeck/engine/spectrum_source.py`
(and the other missing modules) from the VM.

---

## Wiring into ESPsoup

Drop `frontend/signaldeck.js` into the ESPsoup `www/` directory and load it
**before** `radio.js`. `radio.js` already has a hook:

```js
const radio = (window.__SIGNALDECK__ ? new SignalDeckRadio() : new Radio());
```

`SignalDeckRadio` sets `family: 'C5'` (unlocks the 5 GHz / 5.8 GHz features),
advertises an empty `caps` set (disabling every firmware-gated feature), and
reports `tuneRange: [70, 6000]` MHz with `maxSamples: 16380`. The adapter is a
standalone class and does **not** extend `Radio`.

---

## Feature audit (SignalDeck → ESPsoup)

**Works (host-side, only need `radio.capture`):**

* Spectrum tab FFT (`liveLoop` host fallback) and waterfall
* BLE / GFSK packet decode
* Wi-Fi (`wifibDecode`), nRF, Zigbee
* LoRa decode
* LTE cell search
* RC / WB signal classification
* FPV snapshot analysis (`fpvAnalyze`)
* Remote ID (BLE + Wi-Fi frame path)
* Camera and radar analysis

**Disabled by design (empty `caps`, firmware-gated):**

* `CSPEC` / `CPKT` continuous spectrum & packet views (`shell_cont.js` gates on
  `radio.caps.has(...)`, which is empty → falls back to error message)
* `SWEEP` (also its 80 MS/s rate exceeds the PZSDR's ~56 MHz instantaneous BW)
* `DEMODFM` live FPV video (still-blocked)
* `BIGCAP`, `DDC`, `SPECDB`, `CONT`, `STREAM`, `CGRID`, `CPKT`, `TUNEM`,
  `VFMCOLOR`, `DCCAL`, `PARLIO`, `FWOPT`, `FREQK`, `TEMP`, `CAPT`

No ungated call paths that would crash the app were found — every
firmware-dependent feature checks a capability bit before calling into the
radio.

---

## License

SignalDeck is **GPL-3.0**; `server.py` and `main.py` are unmodified copies with
integration lines added, and `iq_source.py` / `iq_stream.py` import SignalDeck
modules, so the backend inherits **GPL-3.0**.

`frontend/signaldeck.js` is original bridge code and the **only** file that goes
into ESPsoup's `www/`, which is otherwise **all-rights-reserved** and is *not*
redistributed here.

---

## Hard limits (measured, not assumed)

* PZSDR = PlutoSDR clone, **AD9364 (1T1R)**, 70 MHz–6 GHz, ~56 MHz
  instantaneous bandwidth, network data plane (static `192.168.1.10`).
* Verified-stable capture at **8 MS/s**; 20 MS/s is the nominal ceiling.
* Zero-IF (LO == centre) — the LO feed-through DC spur is stripped in the time
  domain (`buf - buf.mean()`), so a non-zero IF would shift the whole spectrum
  axis and break BLE/GFSK.
* Clone's RX gain table is inverted above ~10 dB, so gain is clamped to `[0, 10]`.
