import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { AlertTriangle, ArrowRight, KeyRound, UserPlus, Users, LogIn } from "lucide-react";

export default function LoginPage({ navigate }) {
  const { login, joinTeam, user } = useAuth();
  const [tab, setTab] = useState("login"); // "login" | "join"
  const [teamCode, setTeamCode] = useState("");
  const [name, setName] = useState("");
  const [tz, setTz] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata"
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (tab === "join") {
        await joinTeam(teamCode, name, tz);
      } else {
        await login(teamCode, name);
      }
      navigate("/digests");
    } catch (err) {
      setError(
        err.message ||
          (tab === "join"
            ? "Could not join team with that code."
            : "That team code and name do not match anyone.")
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 460, margin: "40px auto 0" }}>
      <div className="card card-elevated" style={{ padding: "36px 32px" }}>
        {/* Toggle Mode */}
        <div className="tab-pill-group" style={{ marginBottom: 24 }}>
          <button
            type="button"
            className={`tab-pill ${tab === "login" ? "active" : ""}`}
            onClick={() => {
              setTab("login");
              setError(null);
            }}
          >
            <LogIn size={14} />
            <span>Sign in</span>
          </button>
          <button
            type="button"
            className={`tab-pill ${tab === "join" ? "active" : ""}`}
            onClick={() => {
              setTab("join");
              setError(null);
            }}
          >
            <UserPlus size={14} />
            <span>Join team with code</span>
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <KeyRound size={20} color="var(--accent-bright)" />
          <h3 style={{ fontSize: 19, margin: 0 }}>
            {tab === "login" ? "Sign in to your team" : "Join team with code"}
          </h3>
        </div>
        <p className="muted" style={{ fontSize: 13, marginBottom: 22 }}>
          {tab === "login"
            ? "Your team's code, and the name your team knows you by. There are no passwords."
            : "Enter the team code shared by your team or manager, along with your name to join."}
        </p>

        {user && (
          <p className="notice-box notice-info" style={{ fontSize: 13, marginBottom: 18 }}>
            Currently signed in as <strong>{user.display_name}</strong>. Submitting will switch your active session.
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
              <span className="hint">
                {tab === "login"
                  ? "from your team page"
                  : "shared by your manager / local or deployed team"}
              </span>
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
              <span className="hint">
                {tab === "login" ? "as your team lists you" : "how you want to appear on the team"}
              </span>
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Aarav Sharma"
              autoComplete="name"
              disabled={submitting}
              required
            />
          </div>

          {tab === "join" && (
            <div className="form-group">
              <label htmlFor="tz">
                <span>Timezone</span>
                <span className="hint">for standup cycles & cutoffs</span>
              </label>
              <input
                id="tz"
                type="text"
                value={tz}
                onChange={(e) => setTz(e.target.value)}
                placeholder="e.g. Asia/Kolkata or UTC"
                disabled={submitting}
              />
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || !teamCode.trim() || !name.trim()}
            style={{ width: "100%", marginTop: 8 }}
          >
            {submitting ? (
              <span className="loading-spinner" style={{ width: 14, height: 14 }} />
            ) : tab === "login" ? (
              "Sign in"
            ) : (
              "Join team"
            )}{" "}
            {!submitting && <ArrowRight size={14} />}
          </button>
        </form>

        <div
          style={{
            marginTop: 24,
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
          {tab === "login"
            ? "New here? Switch to 'Join team with code' above to create your profile."
            : "One shared team code connects all members seamlessly."}
        </div>
      </div>
    </div>
  );
}
