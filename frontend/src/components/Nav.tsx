import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Control Center", end: true },
  { to: "/investigator", label: "Investigator" },
  { to: "/threshold", label: "Threshold & Cost" },
  { to: "/benchmark", label: "Benchmark" },
];

export function Nav() {
  return (
    <div className="flex items-center gap-2 border-b border-line-2 bg-bg px-2.5 py-1.5">
      <span className="border-r border-line pr-2.5 text-base font-bold tracking-tight">
        RISK<span className="text-red">MESH</span>
      </span>
      <nav className="flex">
        {LINKS.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.end}
            className={({ isActive }) =>
              `border-r border-line-2 px-2.5 py-1 text-xs font-medium ${
                isActive ? "bg-red font-semibold text-white" : "text-ink-2 hover:bg-fill"
              }`
            }
          >
            {l.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
