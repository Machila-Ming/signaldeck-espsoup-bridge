'use strict';
// Complete the localization half: espsoup gives ridDistanceM (distance) but no bearing.
// Validate an initial-bearing (great-circle) formula and demo a full "locate" from the
// receiver's own GPS to the drone/operator coordinates carried in Remote ID.
const fs = require('fs'), vm = require('vm');
const W = process.env.ESPSOUP_WWW || 'E:/Projects/_espsoup_analysis/www/';
const sandbox = { console, TextEncoder, TextDecoder, Uint8Array, Int8Array, Uint16Array, Int16Array, Uint32Array, Int32Array, Float32Array, Float64Array, DataView, ArrayBuffer, Array, Object, Math, JSON, Date, Map, Set, WeakMap, Promise, module: { exports: {} } };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(W + 'remoteid.js', 'utf8'), sandbox, { filename: 'remoteid.js' });
const { ridDistanceM } = sandbox.module.exports;

// Initial bearing (deg, 0=North, 90=East) from (la1,lo1) to (la2,lo2).
function bearingDeg(la1, lo1, la2, lo2) {
  const r = Math.PI / 180, p1 = la1 * r, p2 = la2 * r, dl = (lo2 - lo1) * r;
  const y = Math.sin(dl) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return ((Math.atan2(y, x) / r) + 360) % 360;
}

// --- sanity: cardinal directions from (0,0) ---
const cases = [
  ['north', 1, 0, 0],
  ['east', 0, 1, 90],
  ['south', -1, 0, 180],
  ['west', 0, -1, 270],
];
console.log('bearing cardinal sanity:');
let allOk = true;
for (const [name, la, lo, expect] of cases) {
  const b = bearingDeg(0, 0, la, lo);
  const ok = Math.abs(b - expect) < 1e-6;
  if (!ok) allOk = false;
  console.log('  (0,0) -> ' + name.padEnd(6) + ' = ' + b.toFixed(3) + ' deg (expect ' + expect + ') ' + (ok ? 'OK' : 'FAIL'));
}

// --- full locate demo: receiver at Shanghai, drone 0.01° N, operator 0.01° E ---
const me = { lat: 31.2304, lon: 121.4737 };
const drone = { lat: 31.2404, lon: 121.4737 };
const operator = { lat: 31.2304, lon: 121.4837 };

console.log('\nfull "locate" from receiver GPS:');
for (const [name, t] of [['drone', drone], ['operator', operator]]) {
  const dist = ridDistanceM(me.lat, me.lon, t.lat, t.lon);
  const brg = bearingDeg(me.lat, me.lon, t.lat, t.lon);
  console.log('  ' + name.padEnd(8) + ': ' + Math.round(dist) + ' m @ ' + brg.toFixed(1) + ' deg');
}
const dDrone = ridDistanceM(me.lat, me.lon, drone.lat, drone.lon);
const bDrone = bearingDeg(me.lat, me.lon, drone.lat, drone.lon);
const dOp = ridDistanceM(me.lat, me.lon, operator.lat, operator.lon);
const bOp = bearingDeg(me.lat, me.lon, operator.lat, operator.lon);

const okCardinal = allOk;
const okDrone = Math.abs(bDrone) < 1e-3 && Math.abs(dDrone - 1112) < 5;      // due north, ~1112 m (1 deg lat = const)
const okOp = Math.abs(bOp - 90) < 0.01 && Math.abs(dOp - 951) < 5;           // ~due east: 89.997° (great circle bulges N of E); ~951 m (lon × cos(lat))
console.log('\nexact: bDrone=' + bDrone + ' dDrone=' + dDrone + ' | bOp=' + bOp + ' dOp=' + dOp);
console.log('assertions: cardinal ' + okCardinal + ' | drone(N) ' + okDrone + ' | operator(E) ' + okOp);
console.log(okCardinal && okDrone && okOp ? '\nRESULT: PASS — 距离+方位角定位正确' : '\nRESULT: FAIL');
