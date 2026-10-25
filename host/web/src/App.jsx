import { useEffect, useRef, useState } from "react";
import { useServerState } from "./api.js";
import { clamp01, orderCorners } from "./geometry.js";
import { useUnit } from "./units.js";
import { STAGES, getFlow } from "./flow.js";
import { useFoundFlash } from "./useFoundFlash.js";
import TopBar from "./components/TopBar.jsx";
import VideoPanel from "./components/VideoPanel.jsx";
import Stepper from "./components/Stepper.jsx";
import CalibrateStep from "./components/CalibrateStep.jsx";
import FinderStep from "./components/FinderStep.jsx";
import ScanStep from "./components/ScanStep.jsx";
import Advanced from "./components/Advanced.jsx";
import Spinner from "./components/Spinner.jsx";

// Keys that work on every step. Space, Enter, Esc, C, K and T depend on the
// step (below).
const HOTKEYS = {
  r: "reset_studs",
  n: "next_stud",
  l: "laser_toggle",
};
const NUDGE = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

export default function App() {
  const { state, online, command, click } = useServerState();
  const [unit, setUnit] = useUnit();

  // The step on screen comes from the server (shared by every tab). The page
  // only keeps whether the size form is open.
  const [editSize, setEditSize] = useState(false);
  const flow = state ? getFlow(state, { editSize }) : null;
  const flash = useFoundFlash(state);

  const go = (id) => {
    setEditSize(false);
    command("go", id);
  };
  const goBack = () => flow && flow.stageIndex > 0 && go(STAGES[flow.stageIndex - 1].id);

  // Corner box being edited. Lives here because the video (dragging) and the
  // step card (save/cancel) both use it.
  const [box, setBox] = useState(null);
  const [selected, setSelected] = useState(null);
  const editing = !!state && state.wall_size_set && state.clicks < 4 && !editSize && flow.stage === "calibrate";

  const wasEditing = useRef(false);
  useEffect(() => {
    if (editing && !wasEditing.current) {
      setBox(state.corners_norm ? state.corners_norm.map((p) => [...p]) : null);
      setSelected(null);
    }
    wasEditing.current = editing;
  }, [editing, state]);

  const saveCorners = () => box && command("set_corners", { corners: orderCorners(box) });
  const runLaser = () => command("laser_calibrate");
  const adjustBox = () => {
    setEditSize(false);
    command("recalibrate");
  };
  // Back to step 1 with nothing kept from this session.
  const hardRestart = () => {
    command("restart_setup");
    setEditSize(false);
    setBox(null);
    setSelected(null);
  };
  const repick = () => command("resample_object");

  // Keyboard shortcuts. Refs keep the handler current without re-binding.
  const latest = useRef();
  latest.current = { editing, box, selected, saveCorners, command, flow, state, runLaser, adjustBox, repick, go, goBack };
  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
      if (e.target instanceof Element && e.target.closest("input, textarea, select, summary")) return;
      const { editing, box, selected, saveCorners, command, flow, state, runLaser, adjustBox, repick, go, goBack } =
        latest.current;
      if (!flow) return;
      const confirm = e.key === "Enter" || e.key === " ";

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
      if (e.key === "Escape" && !editing) {
        e.preventDefault();
        goBack();
        return;
      }
      // Step 1: Space or Enter starts the laser calibration; Enter moves on once done.
      if (confirm && flow.laserCanStart) {
        e.preventDefault();
        runLaser();
        return;
      }
      if (e.key === "Enter" && flow.stage === "calibrate" && flow.calibrated) {
        e.preventDefault();
        go("finder");
        return;
      }
      if (e.key === "Enter" && flow.stage === "finder" && flow.finderReady) {
        e.preventDefault();
        go("scan");
        return;
      }
      // Step 3: Space is the stud signal when there's no Pro Micro.
      if (e.key === " " && flow.stage === "scan" && state.signal.source === "fake") {
        e.preventDefault();
        command("stud_signal");
        return;
      }
      if (confirm) {
        e.preventDefault(); // don't let Space/Enter click whatever button has focus
        return;
      }
      const key = e.key.toLowerCase();
      const special = {
        k: () => flow.boxDone && !state.laser.calibrating && runLaser(),
        c: () => state.wall_size_set && !state.laser.calibrating && adjustBox(),
        t: () => state.tracker.mode === "object" && repick(),
      };
      if (special[key]) {
        e.preventDefault();
        special[key]();
        return;
      }
      const name = HOTKEYS[key];
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
      <TopBar state={state} onRestart={hardRestart} />
      {!online && (
        <div className="offline">
          Lost contact with the Stud Mapper program. Check that <code>web.py</code> is still running; this page
          reconnects by itself.
        </div>
      )}
      <main className="layout">
        <section className="stage" aria-label="Camera and wall">
          {state && (
            <VideoPanel
              state={state}
              flow={flow}
              flash={flash}
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
              <Stepper index={flow.stageIndex} allowedIndex={flow.allowedIndex} onGo={go} />
              <div className="step-body" key={flow.stage}>
                {flow.stage === "calibrate" && (
                  <CalibrateStep
                    state={state}
                    flow={flow}
                    command={command}
                    editing={editing}
                    box={box}
                    onSaveCorners={saveCorners}
                    unit={unit}
                    setUnit={setUnit}
                    setEditSize={setEditSize}
                    onSkipLaser={() => command("skip_laser")}
                    onRunLaser={runLaser}
                    onNext={() => go("finder")}
                  />
                )}
                {flow.stage === "finder" && (
                  <FinderStep
                    state={state}
                    flow={flow}
                    command={command}
                    onBack={goBack}
                    onNext={() => go("scan")}
                  />
                )}
                {flow.stage === "scan" && <ScanStep state={state} command={command} flash={flash} onBack={goBack} />}
              </div>
              <Advanced
                state={state}
                command={command}
                flow={flow}
                onChangeSize={() => {
                  command("go", "calibrate");
                  setEditSize(true);
                }}
                onAdjustBox={adjustBox}
                onRedoLaser={runLaser}
                onRepick={repick}
              />
            </>
          ) : (
            <p className="card sub connecting">
              <Spinner type="ball-pulse" tone="dark" size="xs" /> Connecting to Stud Mapper…
            </p>
          )}
        </aside>
      </main>
    </>
  );
}
