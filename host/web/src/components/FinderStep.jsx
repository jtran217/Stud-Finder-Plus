import KeyPrompt from "./KeyPrompt.jsx";

export default function FinderStep({ state, flow, command, onBack, onNext }) {
  const object = state.tracker.mode === "object";
  const ready = flow.finderReady;
  const seen = state.tracker.x != null;

  return (
    <section className="card" aria-labelledby="h-step">
      <p className="eyebrow">Step 2 of 3</p>
      <h2 id="h-step">Set up your stud finder</h2>
      <p className="lede">
        {ready
          ? seen
            ? `Locked on. The stud finder is ${state.tracker.x.toFixed(1)} in from the left edge.`
            : "Locked on. Move the stud finder into the box to check it's tracked."
          : object
            ? "Hold the stud finder flat on the wall, inside the box. Then click its colored tag in the video."
            : "Hold the stud finder flat on the wall, inside the box, with marker 10 facing the camera."}
      </p>

      <div className={`finder-hint${ready ? " ok" : ""}`}>
        <FinderPicture ready={ready} />
        <p className="hint">
          {ready
            ? "Move it around: the yellow outline on the video should follow it."
            : object
              ? "Pick something bright that isn't red, so it can't be confused with the laser."
              : "Waiting to see marker 10…"}
        </p>
      </div>

      {ready && <KeyPrompt keys={["Enter"]} label="to start scanning" onClick={onNext} />}

      <div className="row nav">
        <button onClick={onBack}>
          ← Back to calibrate <kbd>Esc</kbd>
        </button>
        {ready && object && (
          <button onClick={() => command("resample_object")}>
            Pick again <kbd>T</kbd>
          </button>
        )}
      </div>
    </section>
  );
}

function FinderPicture({ ready }) {
  const dark = "#26282b";
  return (
    <svg viewBox="0 0 80 56" className="finder-pic" aria-hidden="true">
      <rect x="2" y="2" width="76" height="52" rx="4" fill="none" stroke={dark} strokeWidth="1.5" strokeDasharray="3 2" />
      <rect x="28" y="14" width="24" height="30" rx="4" fill="#f4f4f1" stroke={dark} strokeWidth="1.5" />
      <rect x="33" y="19" width="14" height="9" rx="1.5" fill="#f2c524" stroke={dark} strokeWidth="1.2" />
      <path d="M40 44 l-4 -5 h8 z" fill={dark} />
      {ready ? (
        <rect x="26" y="12" width="28" height="34" rx="5" fill="none" stroke="#2f7d4f" strokeWidth="2" />
      ) : (
        <circle className="pulse" cx="40" cy="23.5" r="9" fill="none" stroke="#2c64c9" strokeWidth="1.5" />
      )}
    </svg>
  );
}
