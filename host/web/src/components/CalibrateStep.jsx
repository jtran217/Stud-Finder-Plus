import { formatLength } from "../units.js";
import KeyPrompt from "./KeyPrompt.jsx";
import LaserSweep from "./LaserSweep.jsx";
import WallSizeForm from "./WallSizeForm.jsx";

// Step 1: size of the scan area, box on the tape crosses, then the laser sweep.
export default function CalibrateStep({ state, flow, command, editing, box, onSaveCorners, unit, setUnit, setEditSize, onSkipLaser, onRunLaser, onNext }) {
  const L = state.laser;
  const sizeText = `${formatLength(state.wall_size[0], unit)} × ${formatLength(state.wall_size[1], unit)} ${unit}`;
  const task = !flow.sizeDone ? "size" : !flow.boxDone ? "box" : flow.laserNeeded && !flow.laserDone ? "laser" : "done";
  const busy = L.calibrating;

  let lede;
  if (task === "size") lede = "First, tell us how big the area you'll scan is.";
  else if (task === "box")
    lede = state.corners_norm
      ? "Check the box still sits on the 4 tape crosses. Drag any corner that moved, then confirm."
      : "Draw a box over the 4 tape crosses on the wall.";
  else if (task === "laser")
    lede = busy
      ? "Watch the wall: the laser is sweeping left to right while the camera measures where it lands."
      : flow.laserFailed
        ? "The camera couldn't find the laser on the wall. Check it's on and pointed inside the box, then try again."
        : "Calibration starts when you press Space. The laser will sweep across the wall.";
  else lede = "Calibration is done. You can adjust the box or run the laser sweep again at any time.";

  return (
    <section className="card" aria-labelledby="h-step">
      <p className="eyebrow">Step 1 of 3</p>
      <h2 id="h-step">Calibrate</h2>
      <p className="lede">{lede}</p>

      <ol className="checklist">
        <li className={task === "size" ? "current" : "done"}>
          <div className="check-head">
            <span>Scan area size</span>
            {task !== "size" && (
              <span className="meta">
                {sizeText}
                <button className="link" disabled={busy} onClick={() => setEditSize(true)}>
                  change
                </button>
              </span>
            )}
          </div>
          {task === "size" && (
            <WallSizeForm
              state={state}
              command={command}
              unit={unit}
              setUnit={setUnit}
              onDone={() => setEditSize(false)}
              onCancel={state.wall_size_set ? () => setEditSize(false) : null}
            />
          )}
        </li>

        <li className={task === "size" ? "" : task === "box" ? "current" : "done"}>
          <div className="check-head">
            <span>Box on the tape crosses</span>
            {task !== "size" && task !== "box" && (
              <span className="meta">
                confirmed
                <button className="link" disabled={busy} onClick={() => command("recalibrate")}>
                  adjust
                </button>
              </span>
            )}
          </div>
          {task === "box" && editing && (
            <>
              <p className="hint">
                {box
                  ? "Drag a corner onto the center of its cross. Click a corner, then arrow keys nudge it."
                  : "Drag across the video to draw a box over the 4 crosses."}
              </p>
              <div className="row">
                <button className="primary" disabled={!box} onClick={onSaveCorners}>
                  Confirm box <kbd>Enter</kbd>
                </button>
              </div>
            </>
          )}
        </li>

        {flow.laserNeeded && (
          <li className={task === "laser" ? (flow.laserFailed ? "current failed" : "current") : task === "done" ? "done" : ""}>
            <div className="check-head">
              <span>Laser</span>
              {task === "laser" && !busy && (
                <button className="link" onClick={onSkipLaser}>
                  skip, map only
                </button>
              )}
            </div>
            {(task === "laser" || task === "done") && <LaserSweep state={state} />}
            {task === "laser" && !busy && (
              <KeyPrompt
                keys={["Space", "Enter"]}
                label={flow.laserFailed ? "to try again" : "to start calibration"}
                onClick={onRunLaser}
                disabled={!flow.laserCanStart}
              />
            )}
          </li>
        )}
      </ol>

      {task === "done" && (
        <>
          <KeyPrompt keys={["Enter"]} label="to continue to the stud finder" onClick={onNext} />
          {flow.laserNeeded && (
            <div className="row center">
              <button onClick={onRunLaser}>
                Run laser calibration again <kbd>K</kbd>
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
