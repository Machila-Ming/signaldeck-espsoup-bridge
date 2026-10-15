"""RF transmitter fingerprinting — learned MLP classifier (numpy backprop).

Upgrades the centroid classifier in demo.py from template-matching to a learned
2-layer MLP on the same features. The network learns to weight them (CFO
dominates), which should beat the centroid's uniform Euclidean distance.

For production swap in a PyTorch CNN that takes raw IQ directly; the data flow
(synth -> bursts -> train -> classify) is identical. Run: python train_mlp.py
"""
import numpy as np

FS = 8e6
N_BURST = 2048
N_TX = 5
N_PER_TX = 40
TRAIN_FRAC = 0.5
TONE = 100e3


def synth_burst(cfo, iq_gain, iq_phase, phase_noise, seed):
    rng = np.random.default_rng(seed)
    n = N_BURST
    t = np.arange(n) / FS
    x = np.exp(1j * 2 * np.pi * TONE * t)
    ramp = min(n // 8, 64)
    env = np.ones(n); env[:ramp] = np.linspace(0, 1, ramp); env[-ramp:] = np.linspace(1, 0, ramp)
    x = x * env
    x = x * np.exp(1j * 2 * np.pi * cfo * t)
    I = np.real(x); Q = iq_gain * (np.cos(iq_phase) * np.imag(x) + np.sin(iq_phase) * I)
    x = I + 1j * Q
    x = x * np.exp(1j * rng.normal(0, phase_noise, n))
    x = x + rng.normal(0, 0.02, n) + 1j * rng.normal(0, 0.02, n)
    return x.astype(np.complex64)


def extract_features(x):
    inst = np.diff(np.unwrap(np.angle(x)))
    cfo = float(np.mean(inst) * FS / (2 * np.pi))
    X = np.fft.fft(x); half = len(X) // 2
    pos = float(np.sum(np.abs(X[1:half]) ** 2)); neg = float(np.sum(np.abs(X[half:]) ** 2))
    iq_imb = neg / (pos + neg + 1e-12)
    spec = np.abs(X[:half]); spec = spec / (np.max(spec) + 1e-12)
    spec_down = spec[:: max(1, half // 64)]
    return np.concatenate([[cfo, iq_imb], spec_down])


def relu(z): return np.maximum(0, z)


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z); return e / e.sum(axis=1, keepdims=True)


def main():
    X, y = [], []
    for i in range(N_TX):
        cfo = (i - N_TX // 2) * 5000.0
        ig = 1.0 + 0.02 * i
        ip = 0.01 * i
        pn = 0.0001 + 0.0002 * i
        for k in range(N_PER_TX):
            X.append(extract_features(synth_burst(cfo, ig, ip, pn, i * 1000 + k)))
            y.append(i)
    X = np.array(X); y = np.array(y)
    idx = np.random.default_rng(0).permutation(len(y))
    X, y = X[idx], y[idx]
    n_tr = int(len(y) * TRAIN_FRAC)
    Xtr, ytr, Xte, yte = X[:n_tr], y[:n_tr], X[n_tr:], y[n_tr:]

    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    Xtr = (Xtr - mu) / sd; Xte = (Xte - mu) / sd

    D, H, K = Xtr.shape[1], 64, N_TX
    rng = np.random.default_rng(1)
    W1 = rng.normal(0, 0.1, (D, H)); b1 = np.zeros(H)
    W2 = rng.normal(0, 0.1, (H, K)); b2 = np.zeros(K)
    Ytr = (np.arange(K) == ytr[:, None]).astype(float)
    lr = 0.5
    for ep in range(300):
        z1 = Xtr @ W1 + b1; a1 = relu(z1)
        z2 = a1 @ W2 + b2; p = softmax(z2)
        dz2 = (p - Ytr) / n_tr
        dW2 = a1.T @ dz2; db2 = dz2.sum(0)
        da1 = dz2 @ W2.T
        dz1 = da1 * (z1 > 0)
        dW1 = Xtr.T @ dz1; db1 = dz1.sum(0)
        W1 -= lr * dW1; b1 -= lr * db1; W2 -= lr * dW2; b2 -= lr * db2
        if ep % 60 == 0:
            loss = -np.mean(np.log(p[np.arange(n_tr), ytr] + 1e-12))
            print('epoch %3d loss %.4f' % (ep, loss))

    z1 = Xte @ W1 + b1; a1 = relu(z1); p = softmax(a1 @ W2 + b2)
    pred = p.argmax(1)
    acc = float(np.mean(pred == yte))
    print('MLP accuracy %.1f%% (centroid was 87%%)' % (acc * 100))
    print('MLP_DONE')


if __name__ == '__main__':
    main()
