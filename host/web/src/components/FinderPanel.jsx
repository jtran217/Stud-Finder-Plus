import { fmt } from "../geometry.js";

export default function FinderPanel({ state, command }) {
  const { tracker, studs, laser } = state;
  const fake = state.signal.source === "fake";
  const x = tracker.x;

  let note = "from the left edge";
  if (state.setup_step) note = "finish setup first";
  else if (x == null) note = `${tracker.name} not in view`;
  else if (state.open_x != null) note = `stud started at ${fmt(state.open_x)} in, keep going`;

  const canAim = laser.calibrated && !laser.calibrating;

  return (
    <section className="block" aria-labelledby="h-scan">
      <h2 id="h-scan">Stud finder</h2>
      <p className={`readout${x == null ? " lost" : ""}`}>
        {fmt(x, 2)}
        <span className="unit">in</span>
      </p>
      <p className="sub">{note}</p>
      <div className="row">
        <button className="primary" disabled={!fake} onClick={() => command("stud_signal")}>
          {state.signal.on ? "End stud" : "Stud signal"} <kbd>Space</kbd>
        </button>
        <button onClick={() => command("reset_studs")}>
          Clear studs <kbd>R</kbd>
        </button>
      </div>

      <ul className="stud-list">
        {studs.length === 0 ? (
          <li className="empty">
            No studs yet. Sweep the stud finder across the wall
            {fake ? ", pressing Space at each edge of a stud" : ""}.
          </li>
        ) : (
          studs.map((s, i) => (
            <li key={i} className={laser.aim_index === i ? "aimed" : undefined}>
              <span>Stud {i + 1}</span>
              <strong>{fmt(s.center)} in</strong>
              {i > 0 ? <span className="gap">{fmt(s.center - studs[i - 1].center)} in apart</span> : <span />}
              <button
                className="aim-btn"
                disabled={!canAim}
                title={`Point the laser at stud ${i + 1}`}
                onClick={() => command("aim", i)}
              >
                Aim
              </button>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}
