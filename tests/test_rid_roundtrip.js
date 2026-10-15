'use strict';
// Self-test: synth a BLE Remote ID (system/operator-position) advertising packet with
// espsoup's own bleSynthPhy, then decode it back with ridBleDecode. Validates the
// packet construction + decode pipeline (no RF) before doing the TX/RX loop.
const fs = require('fs');
const vm = require('vm');
// espsoup www dir (defaults to the local analysis copy; override with ESPSOUP_WWW).
const W = process.env.ESPSOUP_WWW || 'E:/Projects/_espsoup_analysis/www/';
const bleSrc = fs.readFileSync(W + 'ble.js', 'utf8');
const ridSrc = fs.readFileSync(W + 'remoteid.js', 'utf8');

const sandbox = {
  console, TextEncoder, TextDecoder,
  Uint8Array, Int8Array, Uint16Array, Int16Array, Uint32Array, Int32Array,
  Float32Array, Float64Array, DataView, ArrayBuffer,
  Array, Object, Math, JSON, Date, Map, Set, WeakMap, Promise,
  module: { exports: {} },
};
vm.createContext(sandbox);
vm.runInContext(bleSrc, sandbox, { filename: 'ble.js' });
vm.runInContext(ridSrc, sandbox, { filename: 'remoteid.js' });

const { bleSynthPhy } = sandbox;
const { ridBleDecode } = sandbox.module.exports;
console.log('bleSynthPhy =', typeof bleSynthPhy, '| ridBleDecode =', typeof ridBleDecode);

function putI32LE(a, o, x) { a[o] = x & 255; a[o + 1] = (x >> 8) & 255; a[o + 2] = (x >> 16) & 255; a[o + 3] = (x >> 24) & 255; }

// 25-byte Remote ID "system" (type 4) message carrying operator position.
const msg = new Uint8Array(25);
msg[0] = (4 << 4) | 2;         // type 4 (system), protocol version 2
msg[1] = (0 << 2) | 1;         // classification 0, operatorLocationType 1 = Live GNSS
const opLat = Math.round(31.2304 * 1e7);
const opLon = Math.round(121.4737 * 1e7);
putI32LE(msg, 2, opLat);
putI32LE(msg, 6, opLon);
const altE = Math.round((10 + 1000) * 2);   // operator alt 10 m -> encoded 2020
msg[18] = altE & 255; msg[19] = (altE >> 8) & 255;

// BLE advertising PDU: service data 16-bit UUID 0xFFFA, app code 0x0D, counter, 25-byte msg.
const adData = [0xFA, 0xFF, 0x0D, 0x01, ...msg];
const ad = [adData.length + 1, 0x16, ...adData];   // BLE AD length = type byte + data
const advA = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF];
const payload = [...advA, ...ad];
const pdu = [0x42, payload.length, ...payload];

const FS = 8e6, CH = 37;
const iq = bleSynthPhy(pdu, CH, FS, { phy: '1M', snrDb: 40, cfo: 0, leadUs: 100, amp: 0.5 });
console.log('synthesized IQ:', iq.length / 2, 'samples =', (iq.length / 2 / FS * 1e6).toFixed(0), 'us @8MS/s');

const pkts = ridBleDecode(iq, FS, CH);
console.log('decoded packets:', pkts.length);
for (const p of pkts) {
  const rid = p.rid;
  console.log('packet -> rid parsed:', rid ? 'YES' : 'no');
  if (rid) {
    console.log('  transport      :', rid.transport);
    console.log('  operatorLat    :', rid.operatorLat);
    console.log('  operatorLon    :', rid.operatorLon);
    console.log('  operatorAltM   :', rid.operatorAltM);
    console.log('  opLocationType :', rid.operatorLocationType);
    console.log('  EXPECTED       : lat 31.2304, lon 121.4737, alt 10, type "Live GNSS"');
  }
}
