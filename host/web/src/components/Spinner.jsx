import { Loader } from "react-loaders";
import "loaders.css/loaders.min.css";

// tone: light (on video) | dark (on panel) | laser
export default function Spinner({ type = "ball-pulse", tone = "light", size = "sm", label }) {
  return (
    <span className={`spinner spinner-${tone} spinner-${size}`} role="status" aria-label={label}>
      <Loader type={type} active />
    </span>
  );
}
