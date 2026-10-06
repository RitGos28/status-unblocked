import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { CheckCircle2, AlertTriangle, ArrowRight, ShieldCheck } from "lucide-react";

export default function LoginPage({ token, navigate }) {
  const { loginWithToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [member, setMember] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const executeLogin = async () => {
      try {
        setLoading(true);
        setError(null);
        const signedInMember = await loginWithToken(token);
        if (isMounted) {
          setMember(signedInMember);
          setTimeout(() => { navigate("/digests"); }, 900);
        }
      } catch (err) {
        if (isMounted) setError(err.message || "That link is invalid or has expired.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    if (token) executeLogin();
    return () => { isMounted = false; };
  }, [token]);

  return (
    <div style={{ maxWidth: 440, margin: "60px auto 0" }}>
      <div className="card-hero" style={{ textAlign: "center", padding: "44px 36px" }}>
        {loading ? (
          <div className="animate-fade-up">
            <div style={{ marginBottom: 20 }}>
              <span className="loading-spinner" style={{ width: 36, height: 36 }} />
            </div>
            <h3 style={{ fontSize: 19, marginBottom: 8 }}>Signing in…</h3>
            <p className="muted" style={{ fontSize: 13 }}>
              Validating your personal magic link cryptographic token.
            </p>
          </div>
        ) : error ? (
          <div className="animate-fade-up">
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                background: "var(--warn-bg)",
                border: "1px solid var(--warn-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 18px",
              }}
            >
              <AlertTriangle size={26} color="var(--warn)" />
            </div>
            <h3 style={{ fontSize: 19, marginBottom: 8 }}>Authentication Failed</h3>
            <p className="muted" style={{ marginBottom: 22, fontSize: 13 }}>{error}</p>
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => navigate("/")}
              style={{ width: "100%" }}
            >
              Back to start page
            </button>
          </div>
        ) : (
          <div className="animate-fade-up">
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                background: "var(--success-bg)",
                border: "1px solid rgba(52,211,153,0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 18px",
              }}
            >
              <CheckCircle2 size={26} color="var(--success)" />
            </div>
            <h3 style={{ fontSize: 19, marginBottom: 6 }}>
              Welcome, {member ? member.display_name : "Team Member"}!
            </h3>
            <p className="muted" style={{ marginBottom: 22, fontSize: 13 }}>
              Signed in successfully. Redirecting you to your digests…
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate("/digests")}
              style={{ width: "100%" }}
            >
              Continue to Digests <ArrowRight size={14} />
            </button>
          </div>
        )}

        {/* Footer badge */}
        <div
          style={{
            marginTop: 28,
            paddingTop: 18,
            borderTop: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 7,
            color: "var(--text-muted)",
            fontSize: 12,
          }}
        >
          <ShieldCheck size={13} />
          Cryptographically signed, no passwords
        </div>
      </div>
    </div>
  );
}
