import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Notice, Segmented } from "../components/ui";

const MODES = [
  { value: "login", label: "Sign in" },
  { value: "join", label: "Join a team" },
];

export default function LoginPage({ navigate }) {
  const { login, joinTeam, user } = useAuth();
  const [mode, setMode] = useState("login");
  const [teamCode, setTeamCode] = useState("");
  const [name, setName] = useState("");
  const [tz, setTz] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "join") {
        await joinTeam(teamCode, name, tz);
      } else {
        await login(teamCode, name);
      }
      navigate("/digests");
    } catch (err) {
      setError(
        err.message ||
          (mode === "join"
            ? "Could not join a team with that code."
            : "That team code and name do not match anyone.")
      );
    } finally {
      setSubmitting(false);
    }
  };

  const joining = mode === "join";

  return (
    <div className="narrow">
      <div className="row-between mb-16">
        <h1>{joining ? "Join a team" : "Sign in"}</h1>
        <Segmented
          options={MODES}
          value={mode}
          onChange={(v) => {
            setMode(v);
            setError(null);
          }}
        />
      </div>
      <p className="lead mb-24">
        {joining
          ? "Enter the code your team shared with you and the name you want to be listed under."
          : "Your team's code and the name your team lists you under. There are no passwords."}
      </p>

      <div className="card">
        {user && (
          <Notice tone="info">
            You are signed in as {user.display_name}. Signing in again switches who you are.
          </Notice>
        )}
        {error && <Notice tone="danger">{error}</Notice>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="team_code">
              <span>Team code</span>
              <span className="hint">{joining ? "shared by your team" : "on your Team page"}</span>
            </label>
            <input
              id="team_code"
              type="text"
              className="input-caps"
              value={teamCode}
              onChange={(e) => setTeamCode(e.target.value)}
              placeholder="CORE-7K3MQ"
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
              <span className="hint">{joining ? "as it should appear" : "as your team lists you"}</span>
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Aarav Sharma"
              autoComplete="name"
              disabled={submitting}
              required
            />
          </div>

          {joining && (
            <div className="form-group">
              <label htmlFor="tz">
                <span>Time zone</span>
                <span className="hint">sets your standup day</span>
              </label>
              <input
                id="tz"
                type="text"
                value={tz}
                onChange={(e) => setTz(e.target.value)}
                placeholder="Asia/Kolkata"
                spellCheck={false}
                disabled={submitting}
              />
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary btn-block mt-8"
            disabled={submitting || !teamCode.trim() || !name.trim()}
          >
            {submitting ? <span className="loading-spinner" /> : joining ? "Join team" : "Sign in"}
          </button>
        </form>
      </div>

      <p className="muted mt-16">
        {joining
          ? "Already on the team? Use Sign in instead."
          : "New to the team? Choose Join a team and use the same code."}
      </p>
    </div>
  );
}
