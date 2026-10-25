import { useEffect, useRef, useState } from "react";
import { UNITS, formatLength, fromInches, toInches } from "../units.js";

// Width and height of the scan area (between the tape crosses).
export default function WallSizeForm({ state, command, unit, setUnit, onDone, onCancel }) {
  const [width, setWidth] = useState(formatLength(state.wall_size[0], unit));
  const [height, setHeight] = useState(formatLength(state.wall_size[1], unit));
  const widthRef = useRef(null);

  useEffect(() => {
    widthRef.current?.focus();
    widthRef.current?.select();
  }, []);

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
    command("set_wall", { width: toInches(w, unit), height: toInches(h, unit) });
    onDone?.();
  };

  // backend accepts 1-600 in
  const min = fromInches(1, unit);
  const max = fromInches(600, unit);

  return (
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
        <select className="unit-select" aria-label="Unit" value={unit} onChange={(e) => changeUnit(e.target.value)}>
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
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
