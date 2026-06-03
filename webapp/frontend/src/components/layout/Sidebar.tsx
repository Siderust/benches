import { NavLink } from "react-router-dom";
import {
  FlaskConical,
  GitCompareArrows,
  LayoutDashboard,
} from "lucide-react";

const links = [
  { to: "/", icon: LayoutDashboard, label: "Runs" },
  { to: "/compare", icon: GitCompareArrows, label: "Compare Runs" },
];

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
      <div className="flex items-center gap-2 px-5 py-5 border-b border-gray-800">
        <FlaskConical className="h-6 w-6 text-orange-400" />
        <div>
          <span className="font-bold text-lg tracking-tight text-white block leading-tight">
            Siderust Lab
          </span>
          <span className="text-[10px] text-gray-500 uppercase tracking-widest">
            Results Viewer
          </span>
        </div>
      </div>
      <nav className="flex-1 py-4 space-y-1 px-3">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
              }`
            }
          >
            <l.icon className="h-4 w-4" />
            {l.label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 pb-4 text-xs text-gray-600">v1.0.0</div>
    </aside>
  );
}
