import { useEffect, useState } from "react";

// Wipes this session and goes back to step 1. Asks for a second click so a
// stray click can't throw away a scan.
export default function RestartButton({ onRestart, disabled }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 3000);
    return () => clearTimeout(t);
  }, [armed]);

  return (
    <button
      className={`restart${armed ? " armed" : ""}`}
      disabled={disabled}
      onClick={() => {
        if (armed) {
          setArmed(false);
          onRestart();
        } else setArmed(true);
      }}
      title="Clear the size, box, laser calibration, color and studs, and start again from step 1"
    >
      <span aria-hidden="true">↺</span> {armed ? "Click again to restart" : "Restart setup"}
    </button>
  );
}
