import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Check, Copy } from "lucide-react";
import { Avatar, Loading, Notice, PageHeader, SignInRequired } from "../components/ui";

export default function TeamPage({ navigate }) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!user) return undefined;
    let isMounted = true;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getTeam();
        if (isMounted) setData(res);
      } catch (err) {
        if (isMounted) setError(err.message || "Could not load your team.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, [user]);

  if (!user) return <SignInRequired navigate={navigate} what="see your team" />;
  if (loading) return <Loading />;
  if (error || !data) return <Notice tone="danger">{error || "Could not load your team."}</Notice>;

  const { team } = data;
  const members = team.members_detailed || team.members.map((name) => ({ display_name: name }));

  const handleCopy = () => {
    navigator.clipboard.writeText(team.join_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div>
      <PageHeader
        title={team.name}
        lead="Who is on the team, and the code that lets a teammate sign in."
        actions={
          <button type="button" className="btn btn-sm" onClick={() => navigate("/manager")}>
            Manager
          </button>
        }
      />

      <h2>Team code</h2>
      <div className="card">
        <div className="row">
          <code className="code-display">{team.join_code}</code>
          <button type="button" className="btn btn-sm" onClick={handleCopy}>
            {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <p className="muted mt-16">
          Anyone on {team.name} signs in with this code and their name. Everyone on the team can
          see it here. If it leaks, the manager can issue a new one; people already signed in
          stay signed in.
        </p>
      </div>

      <h2>Members ({members.length})</h2>
      <div className="card card-flush">
        <div className="list">
          {members.map((m) => (
            <div key={m.id || m.display_name} className="list-row" style={{ alignItems: "center" }}>
              <Avatar name={m.display_name} />
              <div className="list-main">
                <span className="list-text">{m.display_name}</span>
              </div>
              <span className="muted small">
                {m.tz ? m.tz : ""}
                {m.display_name === user.display_name ? (m.tz ? " · you" : "you") : ""}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
