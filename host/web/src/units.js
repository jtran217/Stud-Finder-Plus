import { useState } from "react";

// The backend works in inches; these are only for entering/showing the wall size.
export const UNITS = {
  in: { label: "in", perInch: 1 },
  ft: { label: "ft", perInch: 1 / 12 },
  cm: { label: "cm", perInch: 2.54 },
  mm: { label: "mm", perInch: 25.4 },
  m: { label: "m", perInch: 0.0254 },
};

export const toInches = (value, unit) => value / UNITS[unit].perInch;
export const fromInches = (inches, unit) => inches * UNITS[unit].perInch;

// Rounded for display: 24 -> "24", 2.0000001 -> "2", 60.96 -> "60.96"
export const formatLength = (inches, unit) =>
  String(Number(fromInches(inches, unit).toFixed(unit === "m" ? 3 : 2)));

const KEY = "stud-mapper-unit";

export function useUnit() {
  const [unit, setUnit] = useState(() => {
    try {
      const saved = localStorage.getItem(KEY);
      return saved in UNITS ? saved : "in";
    } catch {
      return "in";
    }
  });
  const choose = (u) => {
    setUnit(u);
    try {
      localStorage.setItem(KEY, u);
    } catch {
      /* private mode etc. */
    }
  };
  return [unit, choose];
}
