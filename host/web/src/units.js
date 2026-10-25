import { useState } from "react";

// backend is all inches, this is just for the wall size form
export const UNITS = {
  in: { label: "in", perInch: 1 },
  ft: { label: "ft", perInch: 1 / 12 },
  cm: { label: "cm", perInch: 2.54 },
  mm: { label: "mm", perInch: 25.4 },
  m: { label: "m", perInch: 0.0254 },
};

export const toInches = (value, unit) => value / UNITS[unit].perInch;
export const fromInches = (inches, unit) => inches * UNITS[unit].perInch;

// 24 -> "24", 2.0000001 -> "2"
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
      // private mode
    }
  };
  return [unit, choose];
}
