import Loader from "react-loaders";
import "loaders.css/loaders.min.css";

// react-loaders animation, sized and colored for where it sits.
//   type:  any loaders.css name, e.g. "line-scale-pulse-out", "ball-pulse"
//   tone:  "light" (on the dark video), "dark" (on the panel), "laser" (red)
export default function Spinner({ type = "ball-pulse", tone = "light", size = "sm", label }) {
  return (
    <span className={`spinner spinner-${tone} spinner-${size}`} role="status" aria-label={label}>
      <Loader type={type} active />
    </span>
  );
}
