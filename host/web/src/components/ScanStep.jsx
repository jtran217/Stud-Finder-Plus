import { fmt } from "../geometry.js";
import WallRuler from "./WallRuler.jsx";

// Step 3: sweep the wall. Each stud found shows up on the map, and the laser
// jumps to it on its own.
export default function ScanStep({ state, command, flash, onBack }) {
  const { tracker, studs, laser } = state;
  const fake = state.signal.source === "fake";
  const x = tracker.x;
  const canAim = laser.calibrated && !laser.calibrating;

  let title;
  let detail;
  if (x == null) {
    title = "Bring the stud finder into view";
    detail = `The camera can't see the ${tracker.name}. Keep it inside the box.`;
  } else if (state.open_x != null) {
    const last = state.open_edges[state.open_edges.length - 1];
    const from = last.dir > 0 ? "right" : last.dir < 0 ? "left" : "other";
    title = "Now come from the other side";
    detail = `Edge marked at ${fmt(state.open_x)} in. Slide in from the ${from} side until it lights up again.`;
  } else {
    title = studs.length ? "Keep sweeping" : "Sweep the wall";
    detail = fake
      ? "Slide the stud finder slowly across. Press Space each time it lights up."
      : "Slide the stud finder slowly across. When it lights up, that's a stud edge.";
  }

  return (
    <section className="card" aria-labelledby="h-step">
      <p className="eyebrow">Step 3 of 3</p>
      <h2 id="h-step">{title}</h2>
      <p className="lede">{detail}</p>

      <div className="scan-readout">
        <p className={`readout${x == null ? " lost" : ""}`}>
          {fmt(x, 2)}
          <span className="unit">in from the left</span>
        </p>
        {state.open_edges.length > 0 && (
          <span className="pill edge">
            {state.open_edges.length} edge{state.open_edges.length > 1 ? "s" : ""} waiting for a pair
          </span>
        )}
        {fake && (
          <button className={`signal${state.signal.on ? " is-on" : ""}`} onClick={() => command("stud_signal")}>
            {state.signal.on ? "Signal on" : "Stud signal"} <kbd>Space</kbd>
          </button>
        )}
      </div>

      <WallRuler state={state} flash={flash} />

      {state.diag.last_stud_event && state.diag.last_stud_event.ago < 15 && (
        <p className={`last-edge${/ignored/.test(state.diag.last_stud_event.text) ? " bad" : ""}`}>
          Last edge: {state.diag.last_stud_event.text}
        </p>
      )}

      {laser.available !== false && (laser.aim_status || canAim) && (
        <p className="aim">
          <span className="beam-dot" aria-hidden="true" />
          {laser.aim_status || "The laser will point at each stud as you find it."}
        </p>
      )}

      <ul className="stud-list">
        {studs.length === 0 ? (
          <li className="empty">No studs yet. They'll appear here as you find them.</li>
        ) : (
          studs.map((s, i) => (
            <li
              key={i}
              className={[laser.aim_index === i && "aimed", flash && flash.index === i && "flash"].filter(Boolean).join(" ")}
            >
              <span className="num">{i + 1}</span>
              <strong>{fmt(s.center)} in</strong>
              {i > 0 ? <span className="gap">+{fmt(s.center - studs[i - 1].center)} in</span> : <span />}
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

      <div className="row">
        <button disabled={!canAim || !studs.length} onClick={() => command("next_stud")}>
          Next stud <kbd>N</kbd>
        </button>
        <button className={laser.on ? "is-on" : undefined} onClick={() => command("laser_toggle")}>
          {laser.on ? "Laser off" : "Laser on"} <kbd>L</kbd>
        </button>
        <button disabled={!studs.length} onClick={() => command("reset_studs")}>
          Clear studs <kbd>R</kbd>
        </button>
      </div>
      <div className="row nav">
        <button onClick={onBack}>
          ← Back to stud finder <kbd>Esc</kbd>
        </button>
      </div>
    </section>
  );
}
