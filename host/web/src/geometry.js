// points are [x, y] as fractions of the camera image (0-1)

export const clamp01 = (v) => Math.min(1, Math.max(0, v));

// TL, TR, BR, BL
export function orderCorners(pts) {
  const byY = pts.slice().sort((a, b) => a[1] - b[1]);
  const [tl, tr] = byY.slice(0, 2).sort((a, b) => a[0] - b[0]);
  const [bl, br] = byY.slice(2).sort((a, b) => a[0] - b[0]);
  return [tl, tr, br, bl];
}

export function insidePolygon([px, py], poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// where the image actually sits inside the frame (object-fit: contain letterboxes it)
export function pictureRect(img, frame) {
  const fr = frame.getBoundingClientRect();
  const ir = img.getBoundingClientRect();
  const nw = img.naturalWidth || 16;
  const nh = img.naturalHeight || 9;
  const scale = Math.min(ir.width / nw, ir.height / nh);
  const w = nw * scale;
  const h = nh * scale;
  return {
    left: ir.left - fr.left + (ir.width - w) / 2,
    top: ir.top - fr.top + (ir.height - h) / 2,
    w,
    h,
    frameW: fr.width,
    frameH: fr.height,
    frameLeft: fr.left,
    frameTop: fr.top,
  };
}

export const toFramePx = ([x, y], r) => [r.left + x * r.w, r.top + y * r.h];

export const fromClient = (clientX, clientY, r) => [
  clamp01((clientX - r.frameLeft - r.left) / r.w),
  clamp01((clientY - r.frameTop - r.top) / r.h),
];

export const fmt = (v, digits = 1) => (v == null ? "--" : v.toFixed(digits));
