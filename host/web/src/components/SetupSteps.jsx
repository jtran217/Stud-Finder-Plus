import { useEffect, useRef, useState } from "react";
import { UNITS, formatLength, fromInches, toInches } from "../units.js";

export default function SetupSteps({ state, command, editing, box, onSaveCorners, onCancelCorners, unit, setUnit }) {
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
        <WallSizeStep state={state} command={command} unit={unit} setUnit={setUnit} />

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

function WallSizeStep({ state, command, unit, setUnit }) {
  const set = state.wall_size_set;
  const [changing, setChanging] = useState(false);
  const [width, setWidth] = useState(formatLength(state.wall_size[0], unit));
  const [height, setHeight] = useState(formatLength(state.wall_size[1], unit));
  const widthRef = useRef(null);
  const showForm = !set || changing;

  useEffect(() => {
    if (showForm) {
      widthRef.current?.focus();
      widthRef.current?.select();
    }
  }, [showForm]);

  const startChange = () => {
    setWidth(formatLength(state.wall_size[0], unit));
    setHeight(formatLength(state.wall_size[1], unit));
    setChanging(true);
  };

  // Switching units converts what's typed, so 24 in becomes 2 ft.
  const changeUnit = (next) => {
    const convert = (v) => {
      const n = parseFloat(v);
      return n > 0 ? formatLength(toInches(n, unit), next) : v;
    };
    setWidth(convert(width));
    setHeight(convert(height));
    setUnit(next);
  };

  const submit = (e) => {
    e.preventDefault();
    const w = parseFloat(width);
    const h = parseFloat(height);
    if (!(w > 0 && h > 0)) return;
    setChanging(false);
    command("set_wall", { width: toInches(w, unit), height: toInches(h, unit) });
  };

  // backend accepts 1-600 in
  const min = fromInches(1, unit);
  const max = fromInches(600, unit);
  const sizeText = `${formatLength(state.wall_size[0], unit)} × ${formatLength(state.wall_size[1], unit)} ${unit}`;

  return (
    <li className={showForm ? "current" : "done"}>
      <StepHead title="Enter the scan area size" status={showForm ? "" : sizeText} />
      {showForm ? (
        <form className="wall-form" onSubmit={submit}>
          <p className="hint">Measure between the centers of the tape crosses.</p>
          <div className="fields">
            <label htmlFor="wall-w">Width</label>
            <input
              ref={widthRef}
              id="wall-w"
              type="number"
              min={min}
              max={max}
              step="any"
              inputMode="decimal"
              required
              value={width}
              onChange={(e) => setWidth(e.target.value)}
            />
            <select
              className="unit-select"
              aria-label="Unit"
              value={unit}
              onChange={(e) => changeUnit(e.target.value)}
            >
              {Object.keys(UNITS).map((u) => (
                <option key={u} value={u}>
                  {UNITS[u].label}
                </option>
              ))}
            </select>
            <label htmlFor="wall-h">Height</label>
            <input
              id="wall-h"
              type="number"
              min={min}
              max={max}
              step="any"
              inputMode="decimal"
              required
              value={height}
              onChange={(e) => setHeight(e.target.value)}
            />
            <span>{unit}</span>
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
