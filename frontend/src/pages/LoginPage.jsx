import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { AlertTriangle, ArrowRight, KeyRound, Users } from "lucide-react";

export default function LoginPage({ navigate }) {
  const { login, user } = useAuth();
  const [teamCode, setTeamCode] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(teamCode, name);
      navigate("/digests");
    } catch (err) {
      setError(err.message || "That team code and name do not match anyone.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 440, margin: "40px auto 0" }}>
      <div className="card-hero" style={{ padding: "36px 32px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <KeyRound size={20} color="var(--accent-bright)" />
          <h3 style={{ fontSize: 19, margin: 0 }}>Sign in</h3>
        </div>
        <p className="muted" style={{ fontSize: 13, marginBottom: 22 }}>
          Your team's code, and the name your team knows you by. There are no passwords.
        </p>

        {user && (
          <p className="muted" style={{ fontSize: 13, marginBottom: 18 }}>
            You are already signed in as {user.display_name}. Signing in again switches who you are.
          </p>
        )}

        {error && (
          <div className="notice-box notice-warn" style={{ marginBottom: 18 }}>
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="team_code">
              <span>Team code</span>
              <span className="hint">anyone on your team can read it off their Team page</span>
            </label>
            <input
              id="team_code"
              type="text"
              value={teamCode}
              onChange={(e) => setTeamCode(e.target.value)}
              placeholder="e.g. CORE-7K3MQ"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              disabled={submitting}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="name">
              <span>Your name</span>
              <span className="hint">as your team lists you</span>
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Ada Okafor"
              autoComplete="name"
              disabled={submitting}
              required
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || !teamCode.trim() || !name.trim()}
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
          <Users size={13} />
          One code per team, shared by the whole team
        </div>
      </div>
    </div>
  );
}
