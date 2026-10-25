import { useEffect, useRef, useState } from "react";
import { useServerState } from "./api.js";
import { clamp01, orderCorners } from "./geometry.js";
import { useUnit } from "./units.js";
import TopBar from "./components/TopBar.jsx";
import VideoPanel from "./components/VideoPanel.jsx";
import SetupSteps from "./components/SetupSteps.jsx";
import FinderPanel from "./components/FinderPanel.jsx";
import LaserPanel from "./components/LaserPanel.jsx";
import ActivityLog from "./components/ActivityLog.jsx";

const HOTKEYS = {
  c: "recalibrate",
  t: "resample_object",
  " ": "stud_signal",
  r: "reset_studs",
  m: "view",
  k: "laser_calibrate",
  n: "next_stud",
  l: "laser_toggle",
};
const NUDGE = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

export default function App() {
  const { state, online, command, click } = useServerState();
  const [unit, setUnit] = useUnit();

  // Corner box being edited (setup step 2). Lives here because the video
  // (dragging) and the setup panel (save/cancel) both use it.
  const [box, setBox] = useState(null);
  const [selected, setSelected] = useState(null);
  const editing = !!state && state.wall_size_set && state.clicks < 4;

  const wasEditing = useRef(false);
  useEffect(() => {
    if (editing && !wasEditing.current) {
      setBox(state.corners_norm ? state.corners_norm.map((p) => [...p]) : null);
      setSelected(null);
    }
    wasEditing.current = editing;
  }, [editing, state]);

  const saveCorners = () => box && command("set_corners", { corners: orderCorners(box) });
  const cancelCorners = () =>
    state?.corners_norm && command("set_corners", { corners: state.corners_norm });

  // Keyboard shortcuts. Refs keep the handler current without re-binding.
  const latest = useRef();
  latest.current = { editing, box, selected, saveCorners, command };
  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
      if (e.target instanceof Element && e.target.closest("input, textarea, select")) return;
      const { editing, box, selected, saveCorners, command } = latest.current;

      if (editing && e.key === "Enter") {
        e.preventDefault();
        saveCorners();
        return;
      }
      if (editing && NUDGE[e.key] && box && selected != null) {
        e.preventDefault();
        const [dx, dy] = NUDGE[e.key];
        const step = e.shiftKey ? 10 : 1;
        // one camera pixel (1080p) per press
        setBox((b) =>
          b.map((p, i) =>
            i === selected ? [clamp01(p[0] + (dx * step) / 1920), clamp01(p[1] + (dy * step) / 1080)] : p
          )
        );
        return;
      }
      const name = HOTKEYS[e.key.length === 1 ? e.key.toLowerCase() : e.key];
      if (name) {
        e.preventDefault();
        command(name);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <TopBar state={state} />
      {!online && (
        <div className="offline">
          Lost contact with the Stud Mapper program. Check that <code>web.py</code> is still
          running; this page reconnects by itself.
        </div>
      )}
      <main className="layout">
        <section className="stage" aria-label="Camera and wall">
          {state && (
            <VideoPanel
              state={state}
              online={online}
              command={command}
              click={click}
              editing={editing}
              box={box}
              setBox={setBox}
              selected={selected}
              setSelected={setSelected}
              unit={unit}
            />
          )}
        </section>
        <aside className="panel">
          {state ? (
            <>
              <SetupSteps
                state={state}
                command={command}
                editing={editing}
                box={box}
                onSaveCorners={saveCorners}
                onCancelCorners={cancelCorners}
                unit={unit}
                setUnit={setUnit}
              />
              <FinderPanel state={state} command={command} />
              <LaserPanel state={state} command={command} />
              <ActivityLog messages={state.messages} />
            </>
          ) : (
            <p className="block sub">Connecting…</p>
          )}
        </aside>
      </main>
    </>
  );
}
