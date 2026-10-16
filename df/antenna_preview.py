import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

R_ARRAY, N, SOCKET_OD = 20.0, 8, 7.0
BASE_R, BOSS_R = 45.0, 12.0
MOUNT_R, MOUNT_D = 38.0, 4.2
ROD_D = 2.2

fig, ax = plt.subplots(figsize=(7.2, 7.2))
ax.add_patch(Circle((0, 0), BASE_R, facecolor='#dfe8f7', edgecolor='k', lw=1.2))
ax.add_patch(Circle((0, 0), BOSS_R, facecolor='#9fc0ef', edgecolor='k'))
ax.text(0, 0, 'SP8T', ha='center', va='center', fontsize=9)

for k in range(N):
    a = 2 * np.pi * k / N
    x, y = R_ARRAY * np.cos(a), R_ARRAY * np.sin(a)
    ax.add_patch(Circle((x, y), SOCKET_OD / 2, facecolor='#f6c26b', edgecolor='k'))
    ax.add_patch(Circle((x, y), ROD_D / 2, facecolor='white', edgecolor='k'))
    ax.text(1.28 * x, 1.28 * y, 'E%d' % k, ha='center', va='center', fontsize=8)

for k in range(3):
    a = 2 * np.pi * k / 3 + np.pi / 6
    x, y = MOUNT_R * np.cos(a), MOUNT_R * np.sin(a)
    ax.add_patch(Circle((x, y), MOUNT_D / 2, facecolor='white', edgecolor='k', ls='--'))

ax.plot([0, R_ARRAY], [0, 0], 'r--', lw=1)
ax.text(R_ARRAY / 2, 1.5, 'R=20', color='r', fontsize=8, ha='center')
ax.plot([0, BASE_R], [-14, -14], 'k-', lw=1)
ax.text(BASE_R / 2, -12.5, 'base R=45', fontsize=8, ha='center')

ax.set_aspect('equal')
ax.set_xlim(-52, 52); ax.set_ylim(-52, 52)
ax.set_title('8-element pseudo-Doppler holder - top view (mm)')
ax.set_xlabel('mm'); ax.set_ylabel('mm')
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('/tmp/antenna_array_preview.png', dpi=115)
print('PREVIEW_DONE')
