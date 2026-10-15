# espsoup-radio

Minimal standalone raw-IQ capture backend for the ESPsoup frontend. Replaces the
SignalDeck dependency (we only ever used its ~100-line `SDRDevice` wrapper and `/ws/iq`).

- Opens **SoapySDR** directly (`plutosdr` driver).
- Serves **`/ws/iq`** (capture) and **`/api/health`**.
- No scanner / database / auth / spectrum-source — one device, one capture path.

## Run

```bash
# SoapySDR + libiio + plutosdr driver are system-level (install once, outside pip).
pip install -r requirements.txt
python app.py                      # uvicorn on 0.0.0.0:8080
# or:
python -m uvicorn app:app --host 0.0.0.0 --port 8080
```

## Protocol (`/ws/iq`)

```jsonc
-> {"type":"capture","id":1,"freq_hz":2402000000.0,"sample_rate":8000000.0,
    "samples":16380,"gain_db":10.0,"gain_mode":"MANUAL"}
<- {"type":"capture","id":1,"ok":true,"iq_b64":"…","n":16380,"rate":8000000.0,"bits":10,"capture_us":2048}
```

`iq_b64` = interleaved little-endian float32 I/Q, base64. Orientation: native SoapySDR
(`I + jQ`, +f above LO) — matches ESPsoup's `unpackIq` expectation.

## Why 10 dB gain default

The PZSDR clone's RX gain table is inverted above ~10 dB; 10 dB is the top of the
stable range and beats the too-weak 0 dB default (measured ~12× more signal).
