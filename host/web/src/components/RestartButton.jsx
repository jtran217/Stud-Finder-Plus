import { useEffect, useState } from "react";

// needs a second click so you can't wipe a scan by accident
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
