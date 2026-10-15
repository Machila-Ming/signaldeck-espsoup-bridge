'use strict';
// Test the real SignalDeck /ws/iq bridge: connect, ping, request one capture.
const URL = process.argv[2] || 'ws://192.168.144.128:8080/ws/iq';
console.log('connecting to', URL);
const ws = new WebSocket(URL);
let capSent = false;
const t = setTimeout(() => { console.log('TIMEOUT'); try { ws.close(); } catch {} process.exit(0); }, 20000);
ws.onopen = () => { console.log('OPEN'); ws.send(JSON.stringify({ type: 'ping', id: 0 })); };
ws.onmessage = (ev) => {
  const s = String(ev.data);
  console.log('MSG:', s.slice(0, 200));
  let m; try { m = JSON.parse(s); } catch { return; }
  if (m.type === 'pong' && !capSent) {
    capSent = true;
    console.log('-> sending capture: 8 MS/s @ 2402 MHz, 16380 samples');
    ws.send(JSON.stringify({ type: 'capture', id: 1, freq_hz: 2402e6, sample_rate: 8e6, samples: 16380, gain_db: 10, gain_mode: 'MANUAL' }));
  } else if (m.type === 'capture') {
    console.log('CAPTURE ok=' + m.ok + ' n=' + m.n + ' rate=' + m.rate + ' bits=' + m.bits + ' iq_b64_len=' + (m.iq_b64 ? m.iq_b64.length : 0) + ' msg=' + (m.message || ''));
    clearTimeout(t); ws.close(); process.exit(0);
  }
};
ws.onerror = (e) => console.log('ERROR', e.message || String(e));
ws.onclose = (e) => { console.log('CLOSED code=' + e.code + ' reason=' + e.reason); clearTimeout(t); process.exit(0); };
