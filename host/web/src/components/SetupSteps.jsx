import { useEffect, useRef, useState } from "react";

export default function SetupSteps({ state, command, editing, box, onSaveCorners, onCancelCorners }) {
  const wallSet = state.wall_size_set;
  const needObject = state.tracker.mode === "object";
  const objectReady = state.tracker.ready;
  const studCount = state.studs.length;

  const cornersClass = !wallSet ? "" : editing ? "current" : "done";
  const objectClass = !needObject ? "skip" : !wallSet || editing ? "" : objectReady ? "done" : "current";
  const sweepClass = wallSet && !editing && objectReady ? (studCount ? "done" : "current") : "";

  return (
    <section className="block" aria-labelledby="h-setup">
      <h2 id="h-setup">Setup</h2>
      <ol className="steps">
        <WallSizeStep state={state} command={command} />

        <li id="step-corners" className={cornersClass}>
          <StepHead
            title="Fit the box to the tape crosses"
            status={!wallSet ? "" : !editing ? "done" : box ? "drag the corners" : "draw a box"}
          />
          {editing ? (
            <div className="row">
              <button className="primary" disabled={!box} onClick={onSaveCorners}>
                Save corners <kbd>Enter</kbd>
              </button>
              {state.corners_norm && <button onClick={onCancelCorners}>Cancel</button>}
            </div>
          ) : (
            wallSet && (
              <div className="row">
                <button onClick={() => command("recalibrate")}>
                  Adjust corners <kbd>C</kbd>
                </button>
              </div>
            )
          )}
        </li>

        <li className={objectClass}>
          <StepHead title="Pick the stud finder's color" status={objectReady && needObject ? "locked on" : ""} />
          {needObject && objectClass === "done" && (
            <div className="row">
              <button onClick={() => command("resample_object")}>
                Pick again <kbd>T</kbd>
              </button>
            </div>
          )}
        </li>

        <li className={sweepClass}>
          <StepHead
            title="Sweep the wall"
            status={studCount ? `${studCount} stud${studCount > 1 ? "s" : ""} found` : ""}
          />
        </li>
      </ol>
    </section>
  );
}

function StepHead({ title, status }) {
  return (
    <div className="step-head">
      <span className="step-title">{title}</span>
      <span className="step-state">{status}</span>
    </div>
  );
}

function WallSizeStep({ state, command }) {
  const set = state.wall_size_set;
  const [changing, setChanging] = useState(false);
  const [width, setWidth] = useState(String(state.wall_size[0]));
  const [height, setHeight] = useState(String(state.wall_size[1]));
  const widthRef = useRef(null);
  const showForm = !set || changing;

  useEffect(() => {
    if (showForm) {
      widthRef.current?.focus();
      widthRef.current?.select();
    }
  }, [showForm]);

  const startChange = () => {
    setWidth(String(state.wall_size[0]));
    setHeight(String(state.wall_size[1]));
    setChanging(true);
  };

  const submit = (e) => {
    e.preventDefault();
    const w = parseFloat(width);
    const h = parseFloat(height);
    if (!(w > 0 && h > 0)) return;
    setChanging(false);
    command("set_wall", { width: w, height: h });
  };

  return (
    <li className={showForm ? "current" : "done"}>
      <StepHead
        title="Enter the scan area size"
        status={showForm ? "" : `${state.wall_size[0]} × ${state.wall_size[1]} in`}
      />
      {showForm ? (
        <form className="wall-form" onSubmit={submit}>
          <p className="hint">Measure between the centers of the tape crosses.</p>
          <div className="fields">
            <label htmlFor="wall-w">Width</label>
            <input
              ref={widthRef}
              id="wall-w"
              type="number"
              min="1"
              max="600"
              step="any"
              inputMode="decimal"
              required
              value={width}
              onChange={(e) => setWidth(e.target.value)}
            />
            <span>in</span>
            <label htmlFor="wall-h">Height</label>
            <input
              id="wall-h"
              type="number"
              min="1"
              max="600"
              step="any"
              inputMode="decimal"
              required
              value={height}
              onChange={(e) => setHeight(e.target.value)}
            />
            <span>in</span>
          </div>
          <div className="row">
            <button type="submit" className="primary">
              Save size
            </button>
            {set && (
              <button type="button" onClick={() => setChanging(false)}>
                Cancel
              </button>
            )}
          </div>
        </form>
      ) : (
        <div className="row">
          <button onClick={startChange}>Change size</button>
        </div>
      )}
    </li>
  );
}
