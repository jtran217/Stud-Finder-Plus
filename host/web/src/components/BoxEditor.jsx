import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { clamp01, fromClient, insidePolygon, orderCorners, pictureRect, toFramePx } from "../geometry.js";

const HIT_RADIUS = 18;   // px around a corner handle that grabs it
const LOUPE = 150;       // magnifier size in px
const LOUPE_SPAN = 36;   // camera pixels on each side of the point (~4x zoom)
const YELLOW = "#f2c524";
const DARK = "#26282b";

// Drag on the video to draw a box, then drag each corner onto its tape cross.
// Dragging inside the box moves all of it. A magnifier follows a dragged corner.
export default function BoxEditor({ imgRef, frameRef, box, setBox, selected, setSelected, wallSize, cornersIn }) {
  const drag = useRef(null);
  const loupeRef = useRef(null);
  const [rect, setRect] = useState(null);

  // Re-measure on mount and whenever the window resizes.
  useLayoutEffect(() => {
    const measure = () => imgRef.current && setRect(pictureRect(imgRef.current, frameRef.current));
    measure();
    const img = imgRef.current;
    img.addEventListener("load", measure);
    window.addEventListener("resize", measure);
    return () => {
      img.removeEventListener("load", measure);
      window.removeEventListener("resize", measure);
    };
  }, [imgRef, frameRef]);

  useEffect(() => () => hideLoupe(), []);

  function currentRect() {
    const r = pictureRect(imgRef.current, frameRef.current);
    setRect(r);
    return r;
  }

  function showLoupe(p, r) {
    const img = imgRef.current;
    const canvas = loupeRef.current;
    if (!canvas || !img.naturalWidth) return;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = DARK;
    ctx.fillRect(0, 0, LOUPE, LOUPE);
    try {
      ctx.drawImage(
        img,
        p[0] * img.naturalWidth - LOUPE_SPAN,
        p[1] * img.naturalHeight - LOUPE_SPAN,
        LOUPE_SPAN * 2,
        LOUPE_SPAN * 2,
        0,
        0,
        LOUPE,
        LOUPE
      );
    } catch {
      return;
    }
    const c = LOUPE / 2;
    ctx.strokeStyle = YELLOW;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(c, c - 15);
    ctx.lineTo(c, c + 15);
    ctx.moveTo(c - 15, c);
    ctx.lineTo(c + 15, c);
    ctx.stroke();

    // Sit up and to the right of the pointer, flipping near the edges.
    const [x, y] = toFramePx(p, r);
    let left = x + 24;
    let top = y - LOUPE - 24;
    if (left + LOUPE > r.frameW) left = x - LOUPE - 24;
    if (top < 0) top = y + 24;
    canvas.style.left = `${left}px`;
    canvas.style.top = `${top}px`;
    canvas.style.display = "block";
  }

  function hideLoupe() {
    if (loupeRef.current) loupeRef.current.style.display = "none";
  }

  function onPointerDown(e) {
    e.preventDefault();
    const r = currentRect();
    const p = fromClient(e.clientX, e.clientY, r);
    const px = e.clientX - r.frameLeft;
    const py = e.clientY - r.frameTop;

    const hit = box
      ? box.findIndex((c) => {
          const [cx, cy] = toFramePx(c, r);
          return Math.hypot(cx - px, cy - py) <= HIT_RADIUS;
        })
      : -1;

    if (hit >= 0) {
      drag.current = { type: "corner", i: hit };
      setSelected(hit);
      showLoupe(box[hit], r);
    } else if (box && insidePolygon(p, box)) {
      drag.current = { type: "move", start: p, orig: box };
    } else {
      drag.current = { type: "draw", start: p, prev: box };
      setBox(null);
      setSelected(null);
    }
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e) {
    const d = drag.current;
    if (!d) return;
    const r = rect || currentRect();
    const p = fromClient(e.clientX, e.clientY, r);

    if (d.type === "corner") {
      setBox((b) => b.map((c, i) => (i === d.i ? p : c)));
      showLoupe(p, r);
    } else if (d.type === "move") {
      const dx = p[0] - d.start[0];
      const dy = p[1] - d.start[1];
      setBox(d.orig.map(([x, y]) => [clamp01(x + dx), clamp01(y + dy)]));
    } else {
      const [x0, y0] = d.start;
      setBox([[x0, y0], [p[0], y0], p, [x0, p[1]]]);
      showLoupe(p, r);
    }
  }

  function onPointerUp() {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    hideLoupe();

    if (d.type === "corner" && box) {
      // Keep the array in TL, TR, BR, BL order even if a corner was dragged past another.
      const ordered = orderCorners(box);
      setSelected(ordered.indexOf(box[d.i]));
      setBox(ordered);
    } else if (d.type === "draw") {
      const tiny = !box || Math.abs(box[2][0] - box[0][0]) < 0.02 || Math.abs(box[2][1] - box[0][1]) < 0.02;
      setBox(tiny ? d.prev : orderCorners(box));   // a plain click keeps the old box
    }
  }

  const r = rect;
  return (
    <>
      <svg
        className="box-editor"
        viewBox={r ? `0 0 ${r.frameW} ${r.frameH}` : undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        aria-label="Box over the tape crosses. Drag to draw it, then drag each corner onto its cross."
      >
        {r && box && <Box box={box} r={r} selected={selected} dragging={!!drag.current} wallSize={wallSize} cornersIn={cornersIn} />}
      </svg>
      <canvas ref={loupeRef} className="loupe" width={LOUPE} height={LOUPE} style={{ display: "none" }} />
    </>
  );
}

function Box({ box, r, selected, dragging, wallSize, cornersIn }) {
  const ordered = orderCorners(box);
  const outline = ordered.map((p) => toFramePx(p, r).join(",")).join(" ");
  const [tl, tr, , bl] = ordered.map((p) => toFramePx(p, r));

  return (
    <>
      <polygon className="body" points={outline} fill="rgba(242,197,36,0.14)" stroke={DARK} strokeWidth="4" strokeLinejoin="round" />
      <polygon points={outline} fill="none" stroke={YELLOW} strokeWidth="2" strokeLinejoin="round" pointerEvents="none" />

      {!dragging && (
        <>
          <SizeLabel x={(tl[0] + tr[0]) / 2} y={(tl[1] + tr[1]) / 2} text={`${wallSize[0]} in`} />
          <SizeLabel x={(tl[0] + bl[0]) / 2} y={(tl[1] + bl[1]) / 2} text={`${wallSize[1]} in`} />
        </>
      )}

      {box.map((p, i) => {
        const [x, y] = toFramePx(p, r);
        const k = ordered.indexOf(p);        // which corner this is on screen
        const right = k === 1 || k === 2;
        const radius = selected === i ? 13 : 11;
        const [ix, iy] = cornersIn[k];
        return (
          <g key={i} className="handle">
            <circle cx={x} cy={y} r={radius} fill="rgba(38,40,43,0.15)" stroke={DARK} strokeWidth="4" />
            <circle cx={x} cy={y} r={radius} fill="none" stroke={YELLOW} strokeWidth="2" />
            <path d={`M${x - 6} ${y}H${x + 6}M${x} ${y - 6}V${y + 6}`} stroke={YELLOW} strokeWidth="1.5" />
            <text
              x={x + (right ? 16 : -16)}
              y={y + (k >= 2 ? 26 : -18)}
              textAnchor={right ? "start" : "end"}
              fontSize="12"
              fontWeight="700"
              fill={YELLOW}
              stroke={DARK}
              strokeWidth="3"
              paintOrder="stroke"
            >
              {ix}, {iy}
            </text>
          </g>
        );
      })}
    </>
  );
}

function SizeLabel({ x, y, text }) {
  const w = text.length * 7.4 + 14;
  return (
    <g pointerEvents="none">
      <rect x={x - w / 2} y={y - 11} width={w} height="22" rx="4" fill={DARK} />
      <text x={x} y={y + 4.5} textAnchor="middle" fontSize="13" fontWeight="700" fill={YELLOW}>
        {text}
      </text>
    </g>
  );
}
