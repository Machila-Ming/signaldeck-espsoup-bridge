"""DF array calibration — per-antenna phase offset (pseudo-Doppler V2).

Real antennas / switch / cables add a per-port phase offset phi_k. Without
calibration the recovered bearing is biased. Calibration: transmit from a KNOWN
direction, measure the residual phase per antenna (subtract the known geometric
phase), store it, and subtract it in the demod.

Verified: biased without calibration, correct after.
"""
import numpy as np

C = 3e8
F_RF = 5.8e9
LAM = C / F_RF
R = 0.016
N_ANT = 8
F_ROT = 1000.0
FS = 8e6
DUR = 0.02
TONE = 100e3
K = 2 * np.pi * R / LAM   # modulation index


def synth(bearing_deg, phi_off, seed=0):
    rng = np.random.default_rng(seed)
    n = int(FS * DUR)
    t = np.arange(n) / FS
    T_step = 1.0 / (N_ANT * F_ROT)
    ant = (t / T_step).astype(int) % N_ANT
    theta = ant * (2 * np.pi / N_ANT)
    x = np.exp(1j * 2 * np.pi * TONE * t)
    phase = K * np.cos(np.deg2rad(bearing_deg) - theta) + phi_off[ant]
    x = x * np.exp(1j * phase)
    x = x + rng.normal(0, 0.05, n) + 1j * rng.normal(0, 0.05, n)
    return x.astype(np.complex64), theta, ant


def demod(x, theta, ant, phi_cal=None):
    n = len(x)
    t = np.arange(n) / FS
    phase = np.unwrap(np.angle(x)) - 2 * np.pi * TONE * t
    if phi_cal is not None:
        phase = phase - phi_cal[ant]
    c = np.mean(phase * np.cos(theta))
    s = np.mean(phase * np.sin(theta))
    return float(np.rad2deg(np.arctan2(s, c)))


def calibrate(phi_off):
    """Measure per-antenna phase offset from a known bearing=0 reference."""
    x, theta, ant = synth(0.0, phi_off, seed=99)
    n = len(x)
    t = np.arange(n) / FS
    phase = np.unwrap(np.angle(x)) - 2 * np.pi * TONE * t
    theta_ant = ant * (2 * np.pi / N_ANT)
    # residual per antenna = K*cos(-theta_k) + phi_k ; subtract known K*cos(theta_k)
    known = K * np.cos(theta_ant)
    residual = [np.mean(phase[ant == k] - known[ant == k]) for k in range(N_ANT)]
    return np.array(residual)


def main():
    phi_true = np.deg2rad([0.0, 5.0, -3.0, 8.0, -6.0, 2.0, 7.0, -4.0])   # 8 port offsets (deg)

    x, theta, ant = synth(45.0, phi_true)
    est_raw = demod(x, theta, ant)

    phi_cal = calibrate(phi_true)
    x2, theta2, ant2 = synth(45.0, phi_true, seed=1)
    est_cal = demod(x2, theta2, ant2, phi_cal)

    print('true bearing 45 deg, 8 port phase offsets [0,5,-3,8,-6,2,7,-4] deg:')
    print('  no calibration : %.2f deg (err %+.2f deg)' % (est_raw, est_raw - 45))
    print('  calibrated     : %.2f deg (err %+.2f deg)' % (est_cal, est_cal - 45))
    print('  recovered offsets: [%s] deg' % ', '.join('%.2f' % d for d in np.rad2deg(phi_cal)))
    print('CALIBRATION_DONE')


if __name__ == '__main__':
    main()
