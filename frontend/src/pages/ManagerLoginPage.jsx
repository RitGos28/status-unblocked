import React, { useState, useEffect } from "react";
import { managerApi } from "../api/client";
import { AlertTriangle, ArrowRight, Briefcase, Lock } from "lucide-react";

export default function ManagerLoginPage({ navigate }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    let isMounted = true;
    managerApi
      .me()
      .then((me) => {
        if (!isMounted) return;
        setEnabled(me.enabled);
        if (me.authenticated) navigate("/manager");
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, [navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await managerApi.login(username, password);
      navigate("/manager");
    } catch (err) {
      setError(err.message || "That username and password do not match.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 440, margin: "40px auto 0" }}>
      <div className="card-hero" style={{ padding: "36px 32px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <Briefcase size={20} color="var(--accent-bright)" />
          <h3 style={{ fontSize: 19, margin: 0 }}>Manager portal</h3>
        </div>
        <p className="muted" style={{ fontSize: 13, marginBottom: 22 }}>
          Team admin and progress summaries. This sign-in is separate from a member's team code.
        </p>

        {!enabled && (
          <div className="notice-box notice-warning" style={{ marginBottom: 18 }}>
            <AlertTriangle size={16} />
            <span>
              The manager portal is switched off on this server. Set STANDUP_MANAGER_USERNAME
              and STANDUP_MANAGER_PASSWORD to turn it on.
            </span>
          </div>
        )}

        {error && (
          <div className="notice-box notice-warning" style={{ marginBottom: 18 }}>
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="manager_username">
              <span>Username</span>
            </label>
            <input
              id="manager_username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              spellCheck={false}
              disabled={submitting || !enabled}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="manager_password">
              <span>Password</span>
            </label>
            <input
              id="manager_password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              disabled={submitting || !enabled}
              required
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || !enabled || !username.trim() || !password}
            style={{ width: "100%" }}
          >
            {submitting ? "Signing in…" : "Sign in"} <ArrowRight size={14} />
          </button>
        </form>

        <div
          style={{
            marginTop: 26,
            paddingTop: 16,
            borderTop: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 7,
            color: "var(--text-muted)",
            fontSize: 12,
          }}
        >
          <Lock size={13} />
          Every manager view of someone's words is recorded on their My data page
        </div>
      </div>
    </div>
  );
}
