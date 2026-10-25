import { useEffect, useRef, useState } from "react";
import BoxEditor from "./BoxEditor.jsx";
import Spinner from "./Spinner.jsx";

const STILL = new URLSearchParams(location.search).has("still");

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

  const hint = useVideoHint({ state, flow, editing, box, picking });
  const loaded = useFirstFrame(imgRef, src);

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
      <div
        ref={frameRef}
        className={`video-frame${picking ? " clicking" : ""}${editing ? " editing" : ""}${flash ? " found" : ""}`}
      >
        <img ref={imgRef} id="video" src={src} alt="Live camera view of the wall" onClick={onImageClick} />
        {(!loaded || !online) && (
          <div className="video-wait">
            <Spinner type="line-scale" label="Connecting to the camera" />
            <span>{online ? "Connecting to the camera…" : "Reconnecting…"}</span>
          </div>
        )}
        {hint && loaded && online && (
          <div className={`video-hint ${hint.tone}`} key={hint.text} role="status">
            {hint.tone === "busy" ? (
              <Spinner type="line-scale-pulse-out" tone="laser" size="xs" />
            ) : (
              <span className="hint-dot" aria-hidden="true" />
            )}
            <span>{hint.text}</span>
            {hint.keys && <kbd>{hint.keys}</kbd>}
          </div>
        )}
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
      </div>
    </>
  );
}

// The one short instruction shown over the video, or null. Tones: "action"
// (something to do), "busy" (wait, with a loader), "warn" (something's off).
function useVideoHint({ state, flow, editing, box, picking }) {
  const lost = useLasting(flow.stage === "scan" && state.tracker.x == null, 800);
  if (flow.stage === "calibrate") {
    if (!flow.sizeDone) return { tone: "action", text: "Enter the scan area size on the right" };
    if (editing)
      return box
        ? { tone: "action", text: "Drag each corner onto its tape cross", keys: "Enter to confirm" }
        : { tone: "action", text: "Drag across the video to draw the box" };
    if (state.laser.calibrating) return { tone: "busy", text: "Calibrating the laser… keep the wall clear" };
    if (flow.laserCanStart) return { tone: "action", text: "Ready to calibrate the laser", keys: "Space" };
    return null;
  }
  if (picking) return { tone: "action", text: "Click the colored tag on the stud finder" };
  if (flow.stage === "scan") {
    if (state.laser.aiming) return { tone: "busy", text: "Pointing the laser at the stud…" };
    if (lost) return { tone: "warn", text: "Can't see the stud finder: keep it inside the box" };
  }
  return null;
}

// True once `value` has stayed true for `ms` (so a one-frame blip doesn't show).
function useLasting(value, ms) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!value) {
      setOn(false);
      return;
    }
    const t = setTimeout(() => setOn(true), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return on;
}

// True once the camera stream has drawn a frame (reset when the URL changes).
function useFirstFrame(imgRef, src) {
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    setLoaded(false);
    const t = setInterval(() => {
      if (imgRef.current?.naturalWidth > 0) {
        setLoaded(true);
        clearInterval(t);
      }
    }, 150);
    return () => clearInterval(t);
  }, [imgRef, src]);
  return loaded;
}
