'use strict';
// Full chain: SignalDeck /ws/iq bridge -> IQ -> espsoup ridBleDecode.
const fs = require('fs'), vm = require('vm');
const W = process.env.ESPSOUP_WWW || 'E:/Projects/_espsoup_analysis/www/';
const sandbox = { console, TextEncoder, TextDecoder, Uint8Array, Int8Array, Uint16Array, Int16Array, Uint32Array, Int32Array, Float32Array, Float64Array, DataView, ArrayBuffer, Array, Object, Math, JSON, Date, Map, Set, WeakMap, Promise, module: { exports: {} } };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(W + 'ble.js', 'utf8'), sandbox, { filename: 'ble.js' });
vm.runInContext(fs.readFileSync(W + 'remoteid.js', 'utf8'), sandbox, { filename: 'remoteid.js' });
const { ridBleDecode } = sandbox.module.exports;

const URL = 'ws://192.168.144.128:8080/ws/iq';
const FREQ = 2402e6, RATE = 8e6, NSAMP = 16380, CH = 37, MAX = 12;
const t = setTimeout(() => { console.log('TIMEOUT'); process.exit(0); }, 30000);
const ws = new WebSocket(URL);
let done = 0, found = 0, meanSum = 0;

ws.onopen = () => ws.send(JSON.stringify({ type: 'ping', id: 0 }));
ws.onmessage = (ev) => {
  const m = JSON.parse(String(ev.data));
  if (m.type === 'pong') { ws.send(JSON.stringify({ type: 'capture', id: 1, freq_hz: FREQ, sample_rate: RATE, samples: NSAMP, gain_db: 10, gain_mode: 'MANUAL' })); return; }
  if (m.type !== 'capture') return;
  if (m.ok) {
    const bin = Buffer.from(m.iq_b64, 'base64');
    const f32 = new Float32Array(bin.buffer, bin.byteOffset, bin.length / 4);
    let s = 0; for (let i = 0; i < f32.length; i++) s += f32[i] * f32[i];
    meanSum += Math.sqrt(s / f32.length);
    const pk = ridBleDecode(f32, m.rate, CH);
    if (pk.length) { found += pk.length; for (const p of pk) console.log('  BLE pkt:', JSON.stringify({ mac: p.mac, type: p.type, rid: p.rid ? { id: p.rid.id, opLat: p.rid.operatorLat } : null })); }
  } else { console.log('  capture failed:', m.message); }
  done++;
  if (done < MAX) ws.send(JSON.stringify({ type: 'capture', id: done + 1, freq_hz: FREQ, sample_rate: RATE, samples: NSAMP, gain_db: 10, gain_mode: 'MANUAL' }));
  else {
    console.log('captures:', done, '| total samples:', done * NSAMP, '| meanAmp(avg):', (meanSum / done).toFixed(5), '| BLE packets found:', found);
    clearTimeout(t); process.exit(0);
  }
};
ws.onerror = (e) => console.log('ERROR', e.message || String(e));
ws.onclose = (e) => { console.log('CLOSED', e.code, e.reason); clearTimeout(t); process.exit(0); };
