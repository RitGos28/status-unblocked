import React from "react";
import { ShieldCheck, LogOut, Send, BookOpen, Zap, Users, Database, Briefcase } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export default function Header({ currentPath, navigate }) {
  const { user, logout } = useAuth();

  const handleLogout = async (e) => {
    e.preventDefault();
    await logout();
    navigate("/?signed_out=1");
  };

  const initials = user
    ? user.display_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()
    : "";

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
            <Send size={14} /> Submit
          </button>
          <button
            type="button"
            className={`nav-link ${currentPath.startsWith("/digest") ? "active" : ""}`}
            onClick={() => navigate("/digests")}
          >
            <BookOpen size={14} /> Digests
          </button>
          <button
            type="button"
            className={`nav-link ${currentPath === "/me/team" ? "active" : ""}`}
            onClick={() => navigate("/me/team")}
          >
            <Users size={14} /> Team
          </button>
          <button
            type="button"
            className={`nav-link ${currentPath === "/manager" ? "active" : ""}`}
            onClick={() => navigate("/manager")}
          >
            <Briefcase size={14} /> Manager
          </button>
          <button
            type="button"
            className={`nav-link ${currentPath === "/me/teams" ? "active" : ""}`}
            onClick={() => navigate("/me/teams")}
          >
            <Zap size={14} /> Teams
          </button>
          <button
            type="button"
            className={`nav-link ${currentPath === "/me/data" ? "active" : ""}`}
            onClick={() => navigate("/me/data")}
          >
            <Database size={14} /> My data
          </button>
        </nav>
      )}

      <div className="header-user-meta">
        {user ? (
          <>
            <div className="user-pill">
              <div className="user-avatar">{initials}</div>
              <span style={{ color: "var(--text-secondary)", fontWeight: 500, fontSize: 13 }}>
                {user.display_name}
              </span>
              <span style={{ color: "var(--border-strong)" }}>·</span>
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{user.team_name}</span>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="btn btn-ghost"
              style={{ padding: "6px 10px", fontSize: 13, gap: 5 }}
              title="Sign out"
            >
              <LogOut size={13} />
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => navigate("/login")}
            style={{ padding: "6px 14px", fontSize: 13 }}
          >
            Sign in
          </button>
        )}
      </div>
    </header>
  );
}
