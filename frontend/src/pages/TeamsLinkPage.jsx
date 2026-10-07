import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { Zap, Copy, Check, Info, Link2, Clock } from "lucide-react";

export default function TeamsLinkPage({ navigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const loadTeamsInfo = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getTeamsLink();
        if (isMounted) setData(res);
      } catch (err) {
        if (isMounted) setError(err.message || "Failed to load Teams linking info.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    loadTeamsInfo();
    return () => { isMounted = false; };
  }, []);

  const handleCopy = (code) => {
    navigator.clipboard.writeText(`link ${code}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  };

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "50px 24px" }}>
        <span className="loading-spinner" style={{ width: 28, height: 28 }} />
        <p className="muted" style={{ marginTop: 14 }}>Generating Teams linking token…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "40px 30px" }}>
        <Zap size={30} color="var(--text-muted)" style={{ marginBottom: 14 }} />
        <h3 style={{ marginBottom: 8 }}>Sign In Required</h3>
        <p className="muted" style={{ marginBottom: 20 }}>{error}</p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/")}>
          Go to Home
        </button>
      </div>
    );
  }

  const { teams_enabled, linked, code, minutes, viewer } = data;

  return (
    <div className="stagger">
      <div>
        <h1>Link your Teams account</h1>
        <p className="subtitle">
          So the bot knows which member you are, without asking Microsoft who anyone is.
        </p>
      </div>

      {!teams_enabled ? (
        <div className="card">
          <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--r-md)",
                background: "var(--accent-dim)",
                border: "1px solid var(--accent-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <Info size={18} color="var(--accent-bright)" />
            </div>
            <div>
              <h3 style={{ fontSize: 15, marginBottom: 6 }}>Teams Bot is Disabled</h3>
              <p className="muted" style={{ fontSize: 13 }}>
                The Teams bot is not switched on for this deployment. The web form works without it.
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="card card-elevated" style={{ padding: "28px 28px", maxWidth: "100%", overflow: "hidden" }}>
          {linked && (
            <div className="notice-box notice-info" style={{ marginBottom: 20 }}>
              <Link2 size={16} />
              <span>A Teams account is already linked. Sending the code below replaces it.</span>
            </div>
          )}

          <p style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 14 }}>
            In a 1:1 chat with the bot, send:
          </p>

          <div className="teams-code-block" style={{ maxWidth: "100%", overflow: "hidden" }}>
            <pre className="teams-code-pre">link {code}</pre>
            <button
              type="button"
              className="btn btn-outline"
              style={{ padding: "10px 16px", flexShrink: 0 }}
              onClick={() => handleCopy(code)}
              title="Copy command to clipboard"
            >
              {copied ? (
                <>
                  <Check size={15} color="var(--success)" />
                  Copied
                </>
              ) : (
                <>
                  <Copy size={15} />
                  Copy
                </>
              )}
            </button>
          </div>

          <div className="stat-row" style={{ marginTop: 16 }}>
            <div className="stat-chip">
              <Clock size={12} />
              Expires in <strong>{minutes} min</strong>
            </div>
            <div className="stat-chip">
              <Zap size={12} />
              Links to <strong>{viewer.display_name}</strong>
            </div>
            <div className="stat-chip">
              Single-use
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
