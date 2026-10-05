import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { Bot, Copy, Check, Info } from "lucide-react";

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
        if (isMounted) {
          setData(res);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || "Failed to load Teams linking info.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadTeamsInfo();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleCopy = (code) => {
    navigator.clipboard.writeText(`link ${code}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        <span className="loading-spinner" style={{ width: 28, height: 28 }} />
        <p className="muted" style={{ marginTop: 14 }}>Generating Teams linking token...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <h3>Sign In Required</h3>
        <p className="muted" style={{ marginTop: 8 }}>{error}</p>
        <button
          type="button"
          className="btn btn-primary"
          style={{ marginTop: 16 }}
          onClick={() => navigate("/")}
        >
          Go to Home
        </button>
      </div>
    );
  }

  const { teams_enabled, linked, code, minutes, viewer } = data;

  return (
    <div>
      <h1>Link your Teams account</h1>
      <p className="subtitle">
        So the bot knows which member you are, without asking Microsoft who anyone is.
      </p>

      {!teams_enabled ? (
        <div className="card">
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <Info size={20} color="var(--accent-primary)" />
            <div>
              <h3 style={{ fontSize: 16, marginBottom: 4 }}>Teams Bot is Disabled</h3>
              <p className="muted">
                The Teams bot is not switched on for this deployment. The web form works without it.
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="card card-elevated" style={{ padding: "26px 28px" }}>
          {linked && (
            <div className="notice-box notice-info" style={{ marginBottom: 18 }}>
              <Bot size={18} />
              <span>A Teams account is already linked. Sending the code below replaces it.</span>
            </div>
          )}

          <p style={{ marginTop: 0, color: "var(--text-secondary)" }}>
            In a 1:1 chat with the bot, send:
          </p>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              margin: "12px 0 18px",
            }}
          >
            <pre
              className="raw-display"
              style={{
                margin: 0,
                fontSize: 16,
                padding: "12px 18px",
                flex: 1,
                background: "var(--bg-surface-subtle)",
              }}
            >
              link {code}
            </pre>
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => handleCopy(code)}
              title="Copy command to clipboard"
            >
              {copied ? <Check size={16} color="var(--success)" /> : <Copy size={16} />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>

          <p className="muted" style={{ marginBottom: 0 }}>
            This code works once you send it, expires in <strong>{minutes} minutes</strong>, and only links to <strong>{viewer.display_name}</strong>.
          </p>
        </div>
      )}
    </div>
  );
}
