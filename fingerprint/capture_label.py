"""Capture labeled IQ bursts from the espsoup-radio backend for RF fingerprinting.

Usage:
    python capture_label.py <label> <count> <out.npz> [--freq 2.402e9] [--rate 8e6] [--samples 16380]

Captures `count` IQ windows from /ws/iq, labels them `<label>`, saves
X (count x samples complex64) + labels to out.npz. Run once per transmitter;
a later train script loads every *.npz in a directory and maps labels -> classes.

Why this exists: the fingerprint pipeline (demo.py / train_mlp.py) is verified on
synthetic data; this is the real-data glue — same backend, same IQ format, now
labeled for training.
"""
import asyncio, argparse, base64, json
import numpy as np
import websockets

URL = 'ws://192.168.144.128:8080/ws/iq'


async def capture_one(ws, i, freq, rate, samples, gain_db, gain_mode):
    await ws.send(json.dumps({
        'type': 'capture', 'id': i, 'freq_hz': freq, 'sample_rate': rate,
        'samples': samples, 'gain_db': gain_db, 'gain_mode': gain_mode,
    }))
    while True:
        m = json.loads(await ws.recv())
        if m.get('type') == 'capture' and m.get('id') == i:
            if not m.get('ok'):
                print('capture %d failed: %s' % (i, m.get('message')))
                return None
            b = base64.b64decode(m['iq_b64'])
            f = np.frombuffer(b, dtype=np.float32)
            return (f[0::2] + 1j * f[1::2]).astype(np.complex64)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('label')
    ap.add_argument('count', type=int)
    ap.add_argument('out')
    ap.add_argument('--freq', type=float, default=2.402e9)
    ap.add_argument('--rate', type=float, default=8e6)
    ap.add_argument('--samples', type=int, default=16380)
    ap.add_argument('--gain_db', type=float, default=0.0)
    ap.add_argument('--gain_mode', default='AGC')
    a = ap.parse_args()

    async with websockets.connect(URL) as ws:
        X = []
        for i in range(a.count):
            x = await capture_one(ws, i, a.freq, a.rate, a.samples, a.gain_db, a.gain_mode)
            if x is not None:
                X.append(x)
        X = np.array(X, dtype=np.complex64)
        labels = np.array([a.label] * len(X))
        np.savez(a.out, X=X, labels=labels)
        print('saved %d bursts (label=%s) -> %s' % (len(X), a.label, a.out))
        print('CAPTURE_DONE')


if __name__ == '__main__':
    asyncio.run(main())
