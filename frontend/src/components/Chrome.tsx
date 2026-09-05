import { NavLink, useLocation } from "react-router-dom";
import KbChip from "./KbChip";

export default function Chrome() {
  const { pathname } = useLocation();
  if (pathname === "/") {
    return null;
  }

  return (
    <header className="chrome">
      <NavLink to="/" className="wordmark">
        Pactlify
      </NavLink>
      <nav className="toggle" aria-label="workspace">
        <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
          Admin
        </NavLink>
        <NavLink to="/client" className={({ isActive }) => (isActive ? "active" : "")}>
          Client
        </NavLink>
      </nav>
      <KbChip />
    </header>
  );
}
