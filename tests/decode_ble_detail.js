'use strict';
// Decode a captured interleaved-float32 IQ file with espsoup's BLE stack and print packet detail.
const fs = require('fs'), vm = require('vm');
const W = process.env.ESPSOUP_WWW || 'E:/Projects/_espsoup_analysis/www/';
const sandbox = { console, TextEncoder, TextDecoder, Uint8Array, Int8Array, Uint16Array, Int16Array, Uint32Array, Int32Array, Float32Array, Float64Array, DataView, ArrayBuffer, Array, Object, Math, JSON, Date, Map, Set, WeakMap, Promise, module: { exports: {} } };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(W + 'ble.js', 'utf8'), sandbox, { filename: 'ble.js' });
vm.runInContext(fs.readFileSync(W + 'remoteid.js', 'utf8'), sandbox, { filename: 'remoteid.js' });
const { ridBleDecode } = sandbox.module.exports;

const path = process.argv[2];
const FS = Number(process.argv[3] || 8e6), CH = Number(process.argv[4] || 37);
const buf = fs.readFileSync(path);
const f32 = new Float32Array(buf.buffer, buf.byteOffset, Math.floor(buf.length / 4));
const pk = ridBleDecode(f32, FS, CH);
console.log('file:', path, '| samples:', f32.length / 2, '| channel:', CH, '| packets decoded:', pk.length);
for (const p of pk) {
  const bits = { at: p.at, mac: p.mac, type: p.type, dbfs: typeof p.dbfs === 'number' ? +p.dbfs.toFixed(1) : p.dbfs, cfoKHz: p.cfoKHz, pduLen: p.pdu ? p.pdu.length : undefined };
  if (p.rid) bits.RID = { id: p.rid.id, opLat: p.rid.operatorLat, opLon: p.rid.operatorLon };
  console.log('  ', JSON.stringify(bits));
}
