import React from "react";
import { ShieldCheck, LogOut, Send, BookOpen, Bot } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export default function Header({ currentPath, navigate }) {
  const { user, logout } = useAuth();

  const handleLogout = async (e) => {
    e.preventDefault();
    await logout();
    navigate("/?signed_out=1");
  };

  return (
    <header className="app-header">
      <div className="brand-wrapper" onClick={() => navigate("/")}>
        <ShieldCheck className="brand-icon" />
        <span className="brand-title">Status Unblocked</span>
      </div>

      {user && (
        <nav className="nav-links">
          <button
            type="button"
            className={`nav-link ${currentPath === "/submit" ? "active" : ""}`}
            onClick={() => navigate("/submit")}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Send size={15} /> Submit update
            </span>
          </button>
          <button
            type="button"
            className={`nav-link ${currentPath.startsWith("/digest") ? "active" : ""}`}
            onClick={() => navigate("/digests")}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <BookOpen size={15} /> Digests
            </span>
          </button>
          <button
            type="button"
            className={`nav-link ${currentPath === "/me/teams" ? "active" : ""}`}
            onClick={() => navigate("/me/teams")}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Bot size={15} /> Teams
            </span>
          </button>
        </nav>
      )}

      {user ? (
        <div className="header-user-meta">
          <span>
            <strong>{user.display_name}</strong> &middot; {user.team_name}
          </span>
          <button
            type="button"
            onClick={handleLogout}
            className="btn btn-ghost"
            style={{ padding: "4px 8px", fontSize: 13 }}
            title="Sign out"
          >
            <LogOut size={14} /> Sign out
          </button>
        </div>
      ) : (
        <div className="header-user-meta">
          <span className="muted">Read-only mode</span>
        </div>
      )}
    </header>
  );
}
