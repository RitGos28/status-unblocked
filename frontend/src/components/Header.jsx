import React from "react";
import { LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { Avatar } from "./ui";

const LINKS = [
  { to: "/submit", label: "Submit", match: (p) => p === "/submit" },
  { to: "/digests", label: "Digests", match: (p) => p.startsWith("/digest") || p.startsWith("/evidence") },
  { to: "/me/team", label: "Team", match: (p) => p === "/me/team" },
  { to: "/manager", label: "Manager", match: (p) => p === "/manager" },
  { to: "/me/teams", label: "Teams bot", match: (p) => p === "/me/teams" },
  { to: "/me/data", label: "My data", match: (p) => p === "/me/data" },
];

export default function Header({ currentPath, navigate }) {
  const { user, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    navigate("/?signed_out=1");
  };

  return (
    <header className="app-header">
      <button type="button" className="brand" onClick={() => navigate("/")}>
        <span className="brand-mark" aria-hidden="true" />
        Status Unblocked
      </button>

      {user && (
        <nav className="nav" aria-label="Main">
          {LINKS.map((l) => (
            <button
              key={l.to}
              type="button"
              className={`nav-link ${l.match(currentPath) ? "active" : ""}`}
              onClick={() => navigate(l.to)}
            >
              {l.label}
            </button>
          ))}
        </nav>
      )}

      <div className="header-right">
        {user ? (
          <>
            <span className="user-chip">
              <Avatar name={user.display_name} />
              <strong>{user.display_name}</strong>
              <span>{user.team_name}</span>
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-icon"
              onClick={handleLogout}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut size={14} />
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-sm" onClick={() => navigate("/login")}>
            Sign in
          </button>
        )}
      </div>
    </header>
  );
}
