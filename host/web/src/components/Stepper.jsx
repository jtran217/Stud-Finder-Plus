import { STAGES } from "../flow.js";

// Progress across the top of the panel. Any step already reached can be
// clicked to go back (or forward again).
export default function Stepper({ index, allowedIndex, onGo }) {
  return (
    <ol className="stepper" aria-label="Progress">
      {STAGES.map((s, i) => {
        const done = i < index || (i !== index && i < allowedIndex);
        const cls = i === index ? "current" : done ? "done" : "";
        return (
          <li key={s.id} className={cls}>
            <button
              className="step-btn"
              disabled={i > allowedIndex}
              aria-current={i === index ? "step" : undefined}
              onClick={() => onGo(s.id)}
              title={i > allowedIndex ? "Finish the earlier steps first" : `Go to ${s.label}`}
            >
              <span className="dot">{done ? "✓" : i + 1}</span>
              <span className="label">{s.label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
