"""Amplitude direction finding (RSSI comparison) — synthetic verification.

V1 DF per the roadmap (Hardware-Capability-First-Review): 4 directional antennas
at 0/90/180/270 deg + SP4T switch, read RSSI on each, estimate bearing by
amplitude comparison. Simpler than pseudo-Doppler (V2) — no rotation, just switch
and read RSSI.

Cardioid beam gain(theta_k) = (1 + cos(bearing - theta_k)) / 2:
  RSSI_0   - RSSI_180 = A cos(bearing)
  RSSI_90  - RSSI_270 = A sin(bearing)
  => bearing = atan2(RSSI_90 - RSSI_270, RSSI_0 - RSSI_180)

Note: real precision is limited by beam shape + multipath (the #1 killer at 5.8G
per DF-Amplitude-RSSI-Feasibility), not by this math.
"""
import numpy as np

ANT_ANGLES = np.deg2rad([0, 90, 180, 270])


def synth_rssi(bearing_deg, snr_db=20.0, seed=0):
    rng = np.random.default_rng(seed)
    bearing = np.deg2rad(bearing_deg)
    A = 1.0
    gain = A * (1 + np.cos(bearing - ANT_ANGLES)) / 2      # cardioid
    noise_std = A / (10 ** (snr_db / 20))                   # RSSI measurement noise
    return gain + rng.normal(0, noise_std, len(ANT_ANGLES))


def estimate_bearing(rssi):
    cos_b = rssi[0] - rssi[2]      # RSSI_0 - RSSI_180 = A cos(bearing)
    sin_b = rssi[1] - rssi[3]      # RSSI_90 - RSSI_270 = A sin(bearing)
    return float(np.rad2deg(np.arctan2(sin_b, cos_b)))


def main():
    print('amplitude DF (4 cardioid antennas, RSSI comparison @ 20 dB):')
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
