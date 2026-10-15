'use strict';
// SignalDeck radio adapter: drives espsoup's Spectrum tab and every host-side
// decoder (BLE/GFSK, Wi-Fi, LoRa, …) from SignalDeck's SoapySDR backend instead
// of a WebSerial ESP32.  One capture = one `/ws/iq` round-trip that tunes the
// LO to the centre frequency, reads N samples and returns interleaved float32
// I/Q (already standard orientation, ±1 scale, DC stripped server-side).
//
// This is a standalone class (it does NOT extend Radio) so it can be defined
// before radio.js loads; radio.js:559 instantiates it when __SIGNALDECK__ is
// set.  It re-implements the small surface the app actually calls: run(),
// connected/name getters, connect/shutdown/disconnect/sync, tune/gain/filter/
// apply (no-ops — every parameter is sent per-capture), and capture().

window.__SIGNALDECK__ = true;

function sdB64ToF32(b64) {
  const bin = atob(b64);
  const n = bin.length >> 2;
  const dv = new DataView(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) dv.setUint8(i, bin.charCodeAt(i));
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = dv.getFloat32(i << 2, true);
  return out;
}

class SignalDeckRadio {
  constructor() {
    this.t = null; this.queue = []; this.queued = 0; this.wake = null; this.failed = null;
    this.tail = Promise.resolve();
    this._ws = null; this._wsReady = false; this._id = 0; this._pending = new Map();
    this.reset();
  }

  reset() {
    Object.assign(this, {
      // family 'C5' unlocks the 5 GHz / 5.8 GHz features (app.js + wifiplan +
      // slowcook all gate on it); AD9364 covers 70 MHz–6 GHz continuously.
      family: 'C5',
      identity: 'SignalDeck SoapySDR',
      maxSamples: 16380,
      caps: new Set(),               // empty → host-side BLE/GFSK decode fallback
      gainMin: 0, gainMax: 10, gainStep: 1, bandwidthRange: null,
      rates: [20e6, 16e6, 10e6, 8e6, 4e6],
      bits: [8, 10],
      tuneRange: [70, 6000],
      transport: '', baud: 0,
      cur: { freq: null, gain: null, bw: null, lpf: null },
      dropped: 0, captures: 0,
    });
    this.tuneContinuous = true;      // bands.js: honour the continuous 70–6000 MHz
    this.limits = null; this.bigSamples = 0; this.streamStop = false;
    this.contActive = false; this.contStat = null;
  }

  get connected() { return !!this.t && !this.failed; }
  get name() { return 'SignalDeck'; }

  // Serialize exchanges (kept from Radio.run so the app's capture flow is unchanged).
  run(f) { const p = this.tail.then(f); this.tail = p.catch(() => {}); return p; }

  _url() { return (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws/iq'; }

  async _open() {
    const ws = new WebSocket(this._url());
    ws.binaryType = 'arraybuffer';
    this._ws = ws;
    this._wsReady = false;
    ws.onmessage = ev => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === 'pong') return;
      if (msg.type === 'capture') {
        const p = this._pending.get(msg.id);
        if (!p) return;
        this._pending.delete(msg.id);
        msg.ok ? p.resolve(msg) : p.reject(Error(msg.message || 'capture failed'));
      }
    };
    await new Promise((resolve, reject) => {
      ws.onopen = () => { this._wsReady = true; resolve(); };
      ws.onerror = () => reject(Error('WebSocket connect failed'));
      ws.onclose = () => {
        if (!this._wsReady) { reject(Error('WebSocket closed before open')); return; }
        this.failed = Error('WebSocket closed');
        this.onFailure?.(this.failed);
      };
    });
  }

  async connect(transport, info, baud) {
    return this.run(async () => {
      await this.shutdown();
      this.reset();
      this.t = {};
      this.failed = null;
      this.queue = []; this.queued = 0;
      await this._open();
    });
  }

  async shutdown() {
    const ws = this._ws;
    this._ws = null;
    this._wsReady = false;
    if (ws) { try { ws.onclose = null; ws.onerror = null; ws.close(); } catch {} }
    for (const p of this._pending.values()) p.reject(Error('radio disconnected'));
    this._pending.clear();
    this.t = null;
  }

  disconnect() { return this.run(() => this.shutdown()); }

  async sync() {}
  async tune(mhz) { this.cur.freq = mhz; }
  async gain(mode, index) { this.cur.gain = mode === 'MANUAL' ? 'MANUAL ' + index : 'HARDWARE'; }
  async filter(bw, lpf) { this.cur.bw = bw; this.cur.lpf = lpf; }
  async apply(c) {}

  _request(msg) {
    return new Promise((resolve, reject) => {
      if (!this._ws || this._ws.readyState !== 1 || !this._wsReady) return reject(Error('radio not connected'));
      msg.id = ++this._id;
      const timer = setTimeout(() => { this._pending.delete(msg.id); reject(Error('capture timed out')); }, 30000);
      this._pending.set(msg.id, {
        resolve: r => { clearTimeout(timer); resolve(r); },
        reject: e => { clearTimeout(timer); reject(e); },
      });
      this._ws.send(JSON.stringify(msg));
    });
  }

  async capture(c) {
    return this.run(async () => {
      const resp = await this._request({
        type: 'capture',
        freq_hz: c.freq * 1e6,
        sample_rate: c.rate,
        samples: c.samples,
        gain_db: Math.min(10, Math.max(0, Number(c.gain) || 0)),
        gain_mode: c.gainMode || 'MANUAL',
      });
      return {
        iq: sdB64ToF32(resp.iq_b64),
        n: resp.n,
        captureUs: resp.capture_us,
        rate: resp.rate,
        bits: resp.bits || 10,
      };
    });
  }
}
