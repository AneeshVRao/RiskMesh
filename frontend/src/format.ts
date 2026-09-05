// Shared number formatters -- ported from mockups/api.js's `F` table so the
// two clients render the same numbers the same way.
export const fmt = {
  int: (v: number) => v.toLocaleString("en-US"),
  money: (v: number) =>
    v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  f4: (v: number) => v.toFixed(4),
  f3: (v: number) => v.toFixed(3),
  pct2: (v: number) => (v * 100).toFixed(2) + "%",
  pct1: (v: number) => (v * 100).toFixed(1) + "%",
  pct0: (v: number) => Math.round(v * 100) + "%",
};
