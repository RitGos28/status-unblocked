import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Users, Copy, Check, KeyRound, Briefcase } from "lucide-react";

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

  if (!user) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "40px 30px" }}>
        <Users size={32} color="var(--text-muted)" style={{ marginBottom: 14 }} />
        <h3 style={{ marginBottom: 8 }}>Sign In Required</h3>
        <p className="muted" style={{ marginBottom: 20 }}>
          Sign in with your team's code and your name to see your team.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/login")}>
          Sign in
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 40 }}>
        <span className="loading-spinner" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="notice-box notice-warn">
        <span>{error || "Could not load your team."}</span>
      </div>
    );
  }

  const { team } = data;

  const handleCopy = () => {
    navigator.clipboard.writeText(team.join_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="stagger">
      <div className="page-header">
        <div>
          <h1>{team.name}</h1>
          <p className="subtitle" style={{ marginBottom: 0 }}>
            Your team, and the code that lets a teammate sign in.
          </p>
        </div>
        <div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate("/manager")}
            style={{ fontSize: 13 }}
          >
            <Briefcase size={14} /> Open Manager Dashboard
          </button>
        </div>
      </div>

      <h2>Team code</h2>
      <div className="card card-elevated">
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <KeyRound size={18} color="var(--accent-bright)" />
          <code className="code-inline" style={{ fontSize: 22, letterSpacing: "0.08em", padding: "6px 12px" }}>
            {team.join_code}
          </code>
          <button
            type="button"
            className="btn btn-outline"
            onClick={handleCopy}
            style={{ fontSize: 13, padding: "7px 14px" }}
          >
            {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <p className="muted" style={{ marginTop: 14, marginBottom: 0, fontSize: 13 }}>
          Share it with anyone on {team.name}: they sign in with this code and their name.
          Everyone on the team can see it here. If it leaks, a new code can be issued from the
          backend; nobody already signed in is affected.
        </p>
      </div>

      <h2>Members</h2>
      <div className="card card-elevated" style={{ padding: "6px 22px" }}>
        {team.members.map((member) => (
          <div key={member} className="claim-row">
            <span className="claim-who">{member}</span>
            <div className="claim-content">
              <span className="claim-text muted" style={{ fontSize: 13 }}>
                {member === user.display_name ? "you" : ""}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
