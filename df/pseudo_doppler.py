"""Pseudo-Doppler direction finding — synthetic verification (numpy).

Simulates a 2.4 GHz pseudo-Doppler DF receiver: an 8-antenna circular array
switched at F_ROT introduces a phase modulation whose phase encodes the bearing.
The PZSDR captures IQ and the demod recovers the bearing.

Verifies the SOFTWARE (phase -> bearing) before buying the hardware, the same
"verify with synthetic first" pattern as the espsoup and fingerprint pipelines.

Hardware design (2.4 GHz):
  - 8 antennas in a circle, radius R = 5 cm (modulation index 2*pi*R/lam = 2.51 rad)
  - SP8T microwave switch (HMC244 / PE4259 class), driven at F_ROT = 1 kHz
  - rotation reference = the switch clock (for the demod correlation below)
"""
import numpy as np

C = 3e8
F_RF = 2.4e9
LAM = C / F_RF
R = 0.05          # antenna radius (m)
N_ANT = 8
F_ROT = 1000.0    # switch rotation rate (Hz)
FS = 8e6
DUR = 0.02        # 20 ms = 20 rotations
TONE = 100e3


def synth(bearing_deg, seed=0):
    """Simulate the received signal for a transmitter at `bearing_deg`."""
    rng = np.random.default_rng(seed)
    n = int(FS * DUR)
    t = np.arange(n) / FS
    T_step = 1.0 / (N_ANT * F_ROT)
    ant = (t / T_step).astype(int) % N_ANT          # active antenna index
    theta = ant * (2 * np.pi / N_ANT)               # its angle
    x = np.exp(1j * 2 * np.pi * TONE * t)           # carrier tone
    # pseudo-Doppler phase: (2*pi*R/lam)*cos(bearing - theta_ant)
    x = x * np.exp(1j * (2 * np.pi * R / LAM) * np.cos(np.deg2rad(bearing_deg) - theta))
    x = x + rng.normal(0, 0.05, n) + 1j * rng.normal(0, 0.05, n)
    return x.astype(np.complex64), theta


def demod(x, theta):
    """Recover bearing: correlate the (carrier-removed) phase against cos/sin(theta_ref)."""
    n = len(x)
    t = np.arange(n) / FS
    phase = np.unwrap(np.angle(x))
    phase = phase - 2 * np.pi * TONE * t              # strip known carrier
    c = np.mean(phase * np.cos(theta))                # -> cos(bearing)
    s = np.mean(phase * np.sin(theta))                # -> sin(bearing)
    return np.rad2deg(np.arctan2(s, c))


def main():
    print('bearing recovery (8 antennas, 5 cm radius, 1 kHz rotation):')
    ok = 0
    for b in [0, 45, 90, 135, 180, 225, 270, 315]:
        x, theta = synth(b)
        est = demod(x, theta)
        err = (est - b + 180) % 360 - 180
        ok += abs(err) < 2.0
        print('  true %3d deg -> est %7.2f deg (err %+.2f deg)' % (b, est, err))
    print('within 2 deg: %d/8' % ok)
    print('PSEUDO_DOPPLER_DONE')


if __name__ == '__main__':
    main()
