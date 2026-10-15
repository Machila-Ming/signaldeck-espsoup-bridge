"""Amplitude direction finding (RSSI comparison) — synthetic verification.

V1 DF: N directional antennas around a circle + SP8T switch, read RSSI on each,
estimate bearing by correlating RSSI against cos/sin of the antenna angles
(the DFT fundamental — same math as pseudo-Doppler, but on amplitude not phase).

Cardioid beam gain(theta_k) = (1 + cos(bearing - theta_k)) / 2, so:
  sum_k RSSI_k cos(theta_k) = (A*N/2) cos(bearing)
  sum_k RSSI_k sin(theta_k) = (A*N/2) sin(bearing)
  => bearing = atan2(sum RSSI sin, sum RSSI cos)

Note: real precision is limited by beam shape + multipath (the #1 killer at 5.8G),
not by this math.
"""
import numpy as np

N_ANT = 8
ANT_ANGLES = np.arange(N_ANT) * (2 * np.pi / N_ANT)


def synth_rssi(bearing_deg, snr_db=20.0, seed=0):
    rng = np.random.default_rng(seed)
    bearing = np.deg2rad(bearing_deg)
    A = 1.0
    gain = A * (1 + np.cos(bearing - ANT_ANGLES)) / 2      # cardioid
    noise_std = A / (10 ** (snr_db / 20))                   # RSSI measurement noise
    return gain + rng.normal(0, noise_std, len(ANT_ANGLES))


def estimate_bearing(rssi):
    cos_b = np.sum(rssi * np.cos(ANT_ANGLES))
    sin_b = np.sum(rssi * np.sin(ANT_ANGLES))
    return float(np.rad2deg(np.arctan2(sin_b, cos_b)))


def main():
    print('amplitude DF (8 cardioid antennas, RSSI comparison @ 20 dB):')
    ok = 0
    for b in [0, 45, 90, 135, 180, 225, 270, 315]:
        est = estimate_bearing(synth_rssi(b))
        err = (est - b + 180) % 360 - 180
        ok += abs(err) < 2.0
        print('  true %3d deg -> est %7.2f deg (err %+.2f deg)' % (b, est, err))
    print('within 2 deg: %d/8' % ok)
    print('AMPLITUDE_DF_DONE')


if __name__ == '__main__':
    main()
