"""Cut a perspective view out of an equirectangular panorama, looking toward a given compass bearing.

Convention: the centre column of the panorama faces `pano_heading` (compass degrees, clockwise from north);
columns to the right face larger bearings. The horizon is the middle row. Output pixel (u, v) is the ray through
a pinhole camera with the given horizontal field of view, rotated to look at `bearing` and tilted by `pitch`.
"""

import math

import numpy as np
from PIL import Image


def perspective_view(
    pano: np.ndarray, pano_heading: float, bearing: float, fov_deg: float = 80.0,
    out_w: int = 1024, out_h: int = 768, pitch_deg: float = 0.0, roll_deg: float = 0.0,
) -> np.ndarray:
    """pano is an H x W x 3 uint8 array. Returns an out_h x out_w x 3 uint8 array (bilinear sampling)."""
    h, w = pano.shape[:2]
    f = (out_w / 2) / math.tan(math.radians(fov_deg) / 2)
    u = np.arange(out_w) - (out_w - 1) / 2
    v = np.arange(out_h) - (out_h - 1) / 2
    x, y = np.meshgrid(u, v)  # y grows downwards
    if roll_deg:  # turn the image plane about the optical axis
        r = math.radians(roll_deg)
        x, y = x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)
    z = np.full_like(x, f)
    # tilt about the horizontal axis: positive pitch looks up (rays move towards negative y, which is up in the image)
    p = math.radians(pitch_deg)
    y2 = y * math.cos(p) - z * math.sin(p)
    z2 = z * math.cos(p) + y * math.sin(p)
    lon = math.radians(bearing - pano_heading) + np.arctan2(x, z2)  # radians right of the panorama centre
    lat = np.arctan2(-y2, np.hypot(x, z2))  # up is positive
    sx = ((lon / (2 * math.pi) + 0.5) % 1.0) * w
    sy = np.clip((0.5 - lat / math.pi) * h, 0, h - 1.001)
    x0 = np.floor(sx).astype(int) % w
    x1 = (x0 + 1) % w
    y0 = np.floor(sy).astype(int)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (sx - np.floor(sx))[..., None]
    fy = (sy - y0)[..., None]
    top = pano[y0, x0] * (1 - fx) + pano[y0, x1] * fx
    bottom = pano[y1, x0] * (1 - fx) + pano[y1, x1] * fx
    return np.clip(top * (1 - fy) + bottom * fy, 0, 255).astype(np.uint8)


def crop_to_file(pano_path: str, pano_heading: float, bearing: float, out_path: str, **kw) -> str:
    arr = np.asarray(Image.open(pano_path).convert("RGB"))
    Image.fromarray(perspective_view(arr, pano_heading, bearing, **kw)).save(out_path, quality=92)
    return out_path


def alignment(view: np.ndarray) -> float:
    """How axis-aligned the edges are, from -1 (all diagonal) to +1 (all horizontal or vertical).
    Each gradient (gx, gy) is treated as a complex number z; Re(z^4) / |z|^3 is |z| * cos(4 * angle), which is +|z|
    for axis-aligned edges and -|z| at 45 degrees. Summed over the central region and normalised by edge energy.
    Unlike a vertical-only score, bold horizontal features (awning bands, stripes) do not fool it."""
    g = view.astype(float).mean(axis=2)
    h, w = g.shape
    g = g[h // 8 : h - h // 8, w // 8 : w - w // 8]
    gx = (g[1:-1, 2:] - g[1:-1, :-2]) / 2
    gy = (g[2:, 1:-1] - g[:-2, 1:-1]) / 2
    z = gx + 1j * gy
    mag = np.abs(z)
    return float((z**4).real.sum() / (mag**3 + 1e-9).sum()) if mag.sum() > 0 else 0.0


def level_roll(
    pano: np.ndarray, pano_heading: float, bearing: float, fov_deg: float = 80.0,
    search_deg: float = 30.0, step_deg: float = 3.0,
) -> float:
    """The roll (degrees) that makes the view's edges most axis-aligned, found on small preview renders."""
    best_roll, best_score = 0.0, -1.0
    for roll in np.arange(-search_deg, search_deg + 1e-9, step_deg):
        v = perspective_view(pano, pano_heading, bearing, fov_deg, out_w=240, out_h=180, roll_deg=float(roll))
        s = alignment(v)
        if s > best_score + 1e-6 or (abs(s - best_score) <= 1e-6 and abs(roll) < abs(best_roll)):
            best_roll, best_score = float(roll), s
    return best_roll
