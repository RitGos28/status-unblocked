import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { CheckCircle2, AlertTriangle, ArrowRight } from "lucide-react";

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
          setTimeout(() => {
            navigate("/digests");
          }, 800);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || "That link is invalid or has expired.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    if (token) {
      executeLogin();
    }
    return () => {
      isMounted = false;
    };
  }, [token]);

  return (
    <div style={{ maxWidth: 500, margin: "40px auto 0" }}>
      <div className="card card-elevated" style={{ padding: "32px 30px", textAlign: "center" }}>
        {loading ? (
          <div>
            <span className="loading-spinner" style={{ width: 32, height: 32 }} />
            <h3 style={{ marginTop: 18, fontSize: 18 }}>Signing in...</h3>
            <p className="muted" style={{ marginTop: 8 }}>
              Validating your personal magic link cryptographic token.
            </p>
          </div>
        ) : error ? (
          <div>
            <div style={{ color: "var(--warn)", marginBottom: 12 }}>
              <AlertTriangle size={36} style={{ margin: "0 auto" }} />
            </div>
            <h3 style={{ fontSize: 18, marginBottom: 8 }}>Authentication Failed</h3>
            <p className="muted" style={{ marginBottom: 20 }}>{error}</p>
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => navigate("/")}
            >
              Back to start page
            </button>
          </div>
        ) : (
          <div>
            <div style={{ color: "var(--success)", marginBottom: 12 }}>
              <CheckCircle2 size={36} style={{ margin: "0 auto" }} />
            </div>
            <h3 style={{ fontSize: 18, marginBottom: 8 }}>
              Welcome, {member ? member.display_name : "Team Member"}!
            </h3>
            <p className="muted" style={{ marginBottom: 20 }}>
              Signed in successfully. Redirecting you to your digests...
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate("/digests")}
            >
              Continue to Digests <ArrowRight size={15} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
