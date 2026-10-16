"""Parametric 8-element pseudo-Doppler antenna array holder -> STL.

5.8 GHz lambda/4 monopole array: a base plate carrying 8 short sockets for the
monopole rods on a circle of radius R_ARRAY, plus a center boss for the SP8T
switch and 3 tripod mounting holes.

Print flat (base down, sockets up), PLA/PETG. The rods are the conductors; the
holder is dielectric. Lay a metal ground-plane disc (>= lambda/4 radius) on the
base. Keep the sockets short so the dielectric load on the monopoles stays small.

All dimensions in mm. Edit the parameter block and re-run.
"""
import numpy as np
import trimesh

# --- parameters (mm) ---
R_ARRAY = 20.0      # element circle radius (15-20 for 5.8G, see placement note)
N_ELEM = 8          # SP8T -> 8 elements
ROD_D = 2.2         # rod clearance hole diameter (rod ~2.0)
SOCKET_OD = 7.0     # socket outer diameter
SOCKET_H = 6.0      # socket height above base (keep short: dielectric load)
BASE_R = 45.0       # base radius (ground-plane support)
BASE_T = 3.0        # base thickness
BOSS_R = 12.0       # center boss radius (SP8T mount)
BOSS_H = 5.0        # center boss height
MOUNT_R = 38.0      # tripod mounting-hole circle
MOUNT_D = 4.2       # M4 clearance hole


def cyl(r, h, sec=96):
    return trimesh.creation.cylinder(radius=r, height=h, sections=sec)


parts = []
b = cyl(BASE_R, BASE_T); b.apply_translation([0, 0, BASE_T / 2]); parts.append(b)
for k in range(N_ELEM):
    a = 2 * np.pi * k / N_ELEM
    x, y = R_ARRAY * np.cos(a), R_ARRAY * np.sin(a)
    s = cyl(SOCKET_OD / 2, SOCKET_H)
    s.apply_translation([x, y, BASE_T + SOCKET_H / 2])
    parts.append(s)
bo = cyl(BOSS_R, BOSS_H); bo.apply_translation([0, 0, BASE_T + BOSS_H / 2]); parts.append(bo)

solid = parts[0]
for p in parts[1:]:
    solid = solid.union(p, engine='manifold')

cuts = []
for k in range(N_ELEM):
    a = 2 * np.pi * k / N_ELEM
    x, y = R_ARRAY * np.cos(a), R_ARRAY * np.sin(a)
    c = cyl(ROD_D / 2, BASE_T + SOCKET_H + 8, sec=48)
    c.apply_translation([x, y, (BASE_T + SOCKET_H) / 2])
    cuts.append(c)
for k in range(3):
    a = 2 * np.pi * k / 3 + np.pi / 6
    x, y = MOUNT_R * np.cos(a), MOUNT_R * np.sin(a)
    c = cyl(MOUNT_D / 2, BASE_T + 4, sec=48)
    c.apply_translation([x, y, BASE_T / 2])
    cuts.append(c)

cut = cuts[0]
for c in cuts[1:]:
    cut = cut.union(c, engine='manifold')

res = solid.difference(cut, engine='manifold')
res.export('/tmp/antenna_array_8el.stl')
print('faces', len(res.faces), 'volume_mm3', round(float(res.volume), 1))
print('bbox_mm', np.round(res.bounds, 2).tolist())
print('STL_DONE')
