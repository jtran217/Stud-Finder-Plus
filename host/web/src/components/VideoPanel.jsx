import { useEffect, useRef, useState } from "react";
import BoxEditor from "./BoxEditor.jsx";

const STILL = new URLSearchParams(location.search).has("still");
const VIEW_LABELS = { video: "Video", "object mask": "Object mask", "laser mask": "Laser mask" };

function useStreamUrl(online) {
  // New URL after a reconnect, so the browser reopens the MJPEG stream.
  const [n, setN] = useState(0);
  const wasOnline = useRef(online);
  useEffect(() => {
    if (online && !wasOnline.current) setN((v) => v + 1);
    wasOnline.current = online;
  }, [online]);
  return `${STILL ? "/snapshot.jpg" : "/stream.mjpg"}?${n}`;
}

export default function VideoPanel({ state, online, command, click, editing, box, setBox, selected, setSelected, unit }) {
  const imgRef = useRef(null);
  const frameRef = useRef(null);
  const src = useStreamUrl(online);
  const step = state.setup_step;

  let bannerText = null;
  if (!state.wall_size_set) bannerText = "Enter the distance between the tape crosses in the Setup panel";
  else if (editing)
    bannerText = box
      ? "Drag each corner onto the center of its tape cross, then save corners"
      : "Drag across the video to draw a box over the 4 tape crosses";
  else if (step) bannerText = "Click the colored object on the stud finder";

  // Clicks on the picture pick the stud finder's color (after the corners).
  const onImageClick = (e) => {
    if (!step || editing) return;
    const img = e.currentTarget;
    const r = img.getBoundingClientRect();
    const scale = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight);
    const w = img.naturalWidth * scale;
    const h = img.naturalHeight * scale;
    const fx = (e.clientX - r.left - (r.width - w) / 2) / w;
    const fy = (e.clientY - r.top - (r.height - h) / 2) / h;
    if (fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1) click(fx, fy);
  };

  return (
    <>
      {bannerText && (
        <div className="setup-banner">
          <CornerMap mode={!state.wall_size_set ? "size" : editing ? "corners" : "object"} />
          <p>{bannerText}</p>
        </div>
      )}
      <div ref={frameRef} className={`video-frame${step ? " clicking" : ""}${editing ? " editing" : ""}`}>
        <img ref={imgRef} id="video" src={src} alt="Live camera view of the wall" onClick={onImageClick} />
        {editing && (
          <BoxEditor
            imgRef={imgRef}
            frameRef={frameRef}
            box={box}
            setBox={setBox}
            selected={selected}
            setSelected={setSelected}
            wallSize={state.wall_size}
            unit={unit}
            cornersIn={state.corners_in}
          />
        )}
        <div className="views" role="group" aria-label="Camera view">
          {state.views.map((v) => (
            <button key={v} aria-pressed={v === state.view} onClick={() => command("view", v)}>
              {VIEW_LABELS[v] || v}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

// Little diagram in the banner showing what the current step is about.
function CornerMap({ mode }) {
  const dark = "#26282b";
  return (
    <svg className="corner-map" viewBox="0 0 64 40" aria-hidden="true">
      <rect x="6" y="6" width="52" height="28" fill="none" stroke={dark} strokeWidth="1.5" strokeDasharray="3 2" />
      {mode === "size" && (
        <path d="M10 20 H54 M10 17 V23 M54 17 V23" stroke={dark} strokeWidth="1.5" fill="none" />
      )}
      {mode === "corners" &&
        [[6, 6], [58, 6], [58, 34], [6, 34]].map(([x, y]) => (
          <circle key={`${x},${y}`} cx={x} cy={y} r="3.5" fill={dark} stroke={dark} strokeWidth="1.5" />
        ))}
      {mode === "object" && <rect x="26" y="15" width="12" height="10" rx="2" fill={dark} />}
    </svg>
  );
}
