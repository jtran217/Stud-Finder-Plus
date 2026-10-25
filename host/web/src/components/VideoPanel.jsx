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

export default function VideoPanel({ state, flow, flash, online, command, click, editing, box, setBox, selected, setSelected, unit }) {
  const imgRef = useRef(null);
  const frameRef = useRef(null);
  const src = useStreamUrl(online);
  // Clicks on the picture pick the stud finder's color, only on step 2.
  const picking = flow.stage === "finder" && state.tracker.mode === "object" && !state.tracker.ready;

  let bannerText = null;
  let mode = "size";
  if (flow.stage === "calibrate") {
    if (!flow.sizeDone) bannerText = "Enter the size of the scan area in the panel on the right";
    else if (editing) {
      mode = "corners";
      bannerText = box
        ? "Check each corner sits on the center of its tape cross, then press Enter to confirm"
        : "Drag across the video to draw a box over the 4 tape crosses";
    } else if (state.laser.calibrating) {
      mode = "laser";
      bannerText = "Calibrating: watch the laser sweep across the wall. Red dots mark each measured point.";
    } else if (flow.laserCanStart) {
      mode = "laser";
      bannerText = "Press Space to start calibration";
    }
  } else if (picking) {
    mode = "object";
    bannerText = "Click the colored tag on the stud finder";
  }

  const onImageClick = (e) => {
    if (!picking || editing) return;
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
          <CornerMap mode={mode} />
          <p>{bannerText}</p>
        </div>
      )}
      <div
        ref={frameRef}
        className={`video-frame${picking ? " clicking" : ""}${editing ? " editing" : ""}${flash ? " found" : ""}`}
      >
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
        {flash && (
          <div className="found-toast" key={flash.seq} role="status">
            <span className="found-num">{flash.index + 1}</span>
            <span>
              <strong>
                {flash.new ? "Stud found" : "Stud confirmed"} at {flash.center.toFixed(1)} in
              </strong>
              <small>
                {flash.aimed ? "Laser is pointing at it" : flash.new ? "Added to the map" : `${flash.n} passes averaged`}
              </small>
            </span>
          </div>
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
      {mode === "laser" && <line className="banner-beam" x1="32" x2="32" y1="6" y2="34" stroke="#e3261f" strokeWidth="2.5" />}
    </svg>
  );
}
