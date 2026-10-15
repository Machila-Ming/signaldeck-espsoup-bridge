"""RF transmitter fingerprinting — end-to-end demo (numpy only).

Pipeline: synthetic transmitters -> IQ bursts -> feature extraction -> centroid
classifier -> accuracy. Runs with plain numpy so it works anywhere; swap the
classifier for a CNN/PyTorch later, the feature extraction stays.

Each "transmitter" has a distinct RF fingerprint:
  - CFO          : residual carrier offset (crystal mismatch)
  - IQ imbalance : modulator gain/phase mismatch -> an image component
  - phase noise  : oscillator purity
  - spectral shape : (PA nonlinearity etc.)

Features per burst:
  - cfo      : mean instantaneous frequency (phase-based, finer than FFT)
  - iq_imb   : image-rejection ratio (negative / total frequency energy)
  - spectrum : downsampled normalized magnitude spectrum

Classifier: nearest class centroid (Euclidean) — the simplest template matching.
"""
import numpy as np

FS = 8e6
N_BURST = 2048
N_TX = 5
N_PER_TX = 40
TRAIN_FRAC = 0.5
TONE = 100e3  # payload tone


def synth_burst(cfo, iq_gain, iq_phase, phase_noise, seed):
    rng = np.random.default_rng(seed)
    n = N_BURST
    t = np.arange(n) / FS
    x = np.exp(1j * 2 * np.pi * TONE * t)
    # smooth burst envelope
    ramp = min(n // 8, 64)
    env = np.ones(n)
    env[:ramp] = np.linspace(0, 1, ramp)
    env[-ramp:] = np.linspace(1, 0, ramp)
    x = x * env
    # residual CFO
    x = x * np.exp(1j * 2 * np.pi * cfo * t)
    # IQ imbalance (gain + phase -> image)
    I = np.real(x)
    Q = iq_gain * (np.cos(iq_phase) * np.imag(x) + np.sin(iq_phase) * I)
    x = I + 1j * Q
    # white phase noise
    x = x * np.exp(1j * rng.normal(0, phase_noise, n))
    # AWGN
    x = x + rng.normal(0, 0.02, n) + 1j * rng.normal(0, 0.02, n)
    return x.astype(np.complex64)


def extract_features(x):
    inst = np.diff(np.unwrap(np.angle(x)))
    cfo = float(np.mean(inst) * FS / (2 * np.pi))
    X = np.fft.fft(x)
    half = len(X) // 2
    pos = float(np.sum(np.abs(X[1:half]) ** 2))
    neg = float(np.sum(np.abs(X[half:]) ** 2))
    iq_imb = neg / (pos + neg + 1e-12)
    spec = np.abs(X[:half])
    spec = spec / (np.max(spec) + 1e-12)
    spec_down = spec[:: max(1, half // 64)]
    return np.concatenate([[cfo, iq_imb], spec_down])


def classify(feats, centroids):
    return np.array([int(np.argmin([np.linalg.norm(f - c) for c in centroids])) for f in feats])


def main():
    tx_params = []
    for i in range(N_TX):
        tx_params.append((
            (i - N_TX // 2) * 5000.0,  # cfo: -10000..+10000 Hz (realistic: ±20ppm @2.4G = ±48kHz)
            1.0 + 0.02 * i,            # iq_gain: 1.0..1.08
            0.01 * i,                  # iq_phase: 0..0.04 rad
            0.0001 + 0.0002 * i,       # phase_noise (small & realistic)
            i * 1000,                  # seed base
        ))

    X, y = [], []
    for txi, (cfo, ig, ip, pn, sb) in enumerate(tx_params):
        for k in range(N_PER_TX):
            X.append(extract_features(synth_burst(cfo, ig, ip, pn, sb + k)))
            y.append(txi)
    X = np.array(X); y = np.array(y)

    idx = np.random.default_rng(0).permutation(len(y))
    X, y = X[idx], y[idx]
    n_tr = int(len(y) * TRAIN_FRAC)
    Xtr, ytr, Xte, yte = X[:n_tr], y[:n_tr], X[n_tr:], y[n_tr:]

    centroids = [Xtr[ytr == c].mean(axis=0) for c in range(N_TX)]
    pred = classify(Xte, centroids)
    acc = float(np.mean(pred == yte))

    print('transmitters %d | train %d | test %d | accuracy %.1f%%' % (N_TX, n_tr, len(yte), acc * 100))
    for c in range(N_TX):
        m = yte == c
        if m.sum():
            print('  tx%d: %d/%d correct' % (c, int((pred[m] == c).sum()), int(m.sum())))
    print('FINGERPRINT_DEMO_DONE')


if __name__ == '__main__':
    main()
