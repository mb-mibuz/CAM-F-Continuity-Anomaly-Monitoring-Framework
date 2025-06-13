import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

palette = {
    "orange": "#FABB43",   # frame-storage box
    "grey":   "#6B6B6B",   # dashed arrows / text
    "green":  "#3DBB6F",   # detector-framework box
    "red":    "#F05B46",   # IPC-channel box
    "blue":   "#3A9DD6",   # detector-process box
    "pink":   "#EC407A",
}

# a simple orange➜white➜blue gradient for fill contours
brand_cmap = LinearSegmentedColormap.from_list(
    "orange_white_blue",
    [palette["green"], palette["orange"], palette["red"]],
    N=256
)

S_vals = np.linspace(5, 120, 200)        # take duration  (s)
R_vals = np.linspace(0, 600, 200)        # reset duration (s)
S_grid, R_grid = np.meshgrid(S_vals, R_vals)

def pafr_grid(x_time):
    """PAFR surface for a given per-frame-pair processing time x (s)."""
    return ((R_grid / S_grid) + 1) / x_time

detectors = [
    ("ClockDetector (x = 1.92 s)", 1.92, 4.0, palette["pink"]),
    ("DifferenceDetector (x = 6.37 s)", 6.37, 1.2, palette["pink"]),
]

for label, x_t, sig_rate, sig_colour in detectors:
    Z = pafr_grid(x_t)

    fig, ax = plt.subplots(figsize=(8, 5))

    # filled contours
    cf = ax.contourf(S_grid, R_grid, Z, levels=20, cmap=brand_cmap)

    # signature-rate isoline (solid, brand colour)
    cs_sig = ax.contour(
        S_grid, R_grid, Z,
        levels=[sig_rate],
        colors=[sig_colour], linewidths=2.0
    )
    ax.clabel(cs_sig, fmt=lambda v: f"{v:.1f} fps", colors=sig_colour)

    # 24 fps isoline (dashed, brand orange) if the surface ever hits it
    if Z.max() >= 24:
        cs_24 = ax.contour(
            S_grid, R_grid, Z,
            levels=[24],
            colors=[palette["grey"]],
            linewidths=2.0, linestyles="dashed"
        )
        ax.clabel(cs_24, fmt="24 fps", colors=palette["grey"])

    # styling
    ax.set_title(f"{label} – Production-Aligned Frame Rate", fontweight="bold")
    ax.set_xlabel("Take duration S  (seconds)")
    ax.set_ylabel("Reset duration R (seconds)")
    ax.grid(color=palette["grey"], linestyle="--", alpha=0.3, linewidth=0.6)

    cbar = fig.colorbar(cf, ax=ax)
    cbar.ax.set_ylabel("PAFR  (fps)")

    plt.tight_layout()
    plt.show()
