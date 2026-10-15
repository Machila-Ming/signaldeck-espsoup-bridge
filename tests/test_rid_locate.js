'use strict';
// Validate espsoup's Remote ID localization path: decode -> coordinate merge -> distance.
// No RF: synthesize type 0 (ID), type 1 (drone position), type 4 (operator position),
// merge them through DroneTracker, and check the computed distance against a known value.
const fs = require('fs'), vm = require('vm');
const W = process.env.ESPSOUP_WWW || 'E:/Projects/_espsoup_analysis/www/';
const sandbox = { console, TextEncoder, TextDecoder, Uint8Array, Int8Array, Uint16Array, Int16Array, Uint32Array, Int32Array, Float32Array, Float64Array, DataView, ArrayBuffer, Array, Object, Math, JSON, Date, Map, Set, WeakMap, Promise, module: { exports: {} } };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(W + 'remoteid.js', 'utf8'), sandbox, { filename: 'remoteid.js' });
const RID = sandbox.module.exports;
const { ridApply, ridDistanceM, DroneTracker } = RID;

function putI32LE(a, o, x) { a[o] = x & 255; a[o + 1] = (x >> 8) & 255; a[o + 2] = (x >> 16) & 255; a[o + 3] = (x >> 24) & 255; }

// --- 1. haversine sanity check ---
const d1 = ridDistanceM(0, 0, 0, 1);       // 1 deg longitude at equator ≈ 111195 m
const d2 = ridDistanceM(31.2304, 121.4737, 31.2404, 121.4737);  // 0.01 deg north ≈ 1112 m
console.log('ridDistanceM(0,0 -> 0,1)   =', Math.round(d1), 'm (expect ~111195)');
console.log('ridDistanceM(0.01 deg lat)  =', Math.round(d2), 'm (expect ~1112)');

// --- 2. message builders (25-byte) ---
function msgType0(id) {
  const m = new Uint8Array(25); m[0] = 0x02; m[1] = 0x00;             // type 0, version 2, serial/undeclared
  m.set(new TextEncoder().encode(id).subarray(0, 20), 2); return m;
}
function msgType1(lat, lon, altM) {
  const m = new Uint8Array(25); m[0] = 0x12; m[1] = 0x00;             // type 1, version 2, status 0
  m[2] = 0; m[3] = 0; m[4] = 0;                                        // dir 0, speed 0, vspeed 0
  putI32LE(m, 5, Math.round(lat * 1e7));
  putI32LE(m, 9, Math.round(lon * 1e7));
  const e = Math.round((altM + 1000) * 2);                             // ridAlt = e*0.5 - 1000
  m[13] = e & 255; m[14] = (e >> 8) & 255;                             // altBaro
  m[15] = e & 255; m[16] = (e >> 8) & 255;                             // altGeo
  m[17] = e & 255; m[18] = (e >> 8) & 255;                             // height
  return m;
}
function msgType4(opLat, opLon, opAltM) {
  const m = new Uint8Array(25); m[0] = 0x42; m[1] = 1;                 // type 4, version 2, operatorLocationType 1 (Live GNSS)
  putI32LE(m, 2, Math.round(opLat * 1e7));
  putI32LE(m, 6, Math.round(opLon * 1e7));
  const e = Math.round((opAltM + 1000) * 2);
  m[18] = e & 255; m[19] = (e >> 8) & 255;
  return m;
}

// --- 3. DroneTracker across 3 packets (one message type per BLE advertisement) ---
const OP = { lat: 31.2304, lon: 121.4737, alt: 10 };    // operator (Shanghai)
const DR = { lat: 31.2404, lon: 121.4737, alt: 120 };   // drone 0.01 deg north of operator
const tracker = new DroneTracker();
const MAC = 'AA:BB:CC:DD:EE:FF';
const p0 = tracker.add({ transport: 'ble', mac: MAC, messages: [RID.ridParseMessage(msgType0('DRONE-XYZ-0001'), 0)] });
const p1 = tracker.add({ transport: 'ble', mac: MAC, messages: [RID.ridParseMessage(msgType1(DR.lat, DR.lon, DR.alt), 0)] });
const p2 = tracker.add({ transport: 'ble', mac: MAC, messages: [RID.ridParseMessage(msgType4(OP.lat, OP.lon, OP.alt), 0)] });
const [drone] = tracker.list();

console.log('\nDroneTracker merged drone object:');
for (const k of ['id', 'lat', 'lon', 'heightM', 'operatorLat', 'operatorLon', 'operatorAltM', 'operatorLocationType', 'distanceToOperatorM', 'transport', 'mac', 'msgs']) {
  console.log('  ' + k + ' = ' + (drone[k] ?? null));
}

// --- 4. assertions ---
const expect = ridDistanceM(DR.lat, DR.lon, OP.lat, OP.lon);
const okId = drone.id === 'DRONE-XYZ-0001';
const okLat = Math.abs(drone.lat - DR.lat) < 1e-6 && Math.abs(drone.lon - DR.lon) < 1e-6;
const okOp = Math.abs(drone.operatorLat - OP.lat) < 1e-6 && Math.abs(drone.operatorLon - OP.lon) < 1e-6;
const okDist = Math.abs(drone.distanceToOperatorM - expect) < 1.0;
console.log('\nassertions:');
console.log('  id correct      :', okId);
console.log('  drone pos       :', okLat);
console.log('  operator pos    :', okOp);
console.log('  distance matches:', okDist, '(computed ' + Math.round(drone.distanceToOperatorM) + ' m, expect ' + Math.round(expect) + ' m)');
console.log(okId && okLat && okOp && okDist ? '\nRESULT: PASS — Remote ID 定位链路正确' : '\nRESULT: FAIL');
