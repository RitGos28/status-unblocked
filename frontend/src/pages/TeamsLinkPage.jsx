import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { Check, Copy } from "lucide-react";
import { Loading, Notice, PageHeader, SignInRequired } from "../components/ui";

export default function TeamsLinkPage({ navigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getTeamsLink();
        if (isMounted) setData(res);
      } catch (err) {
        if (isMounted) setError(err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleCopy = (code) => {
    navigator.clipboard.writeText(`link ${code}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) return <Loading />;
  if (error && error.status === 401) return <SignInRequired navigate={navigate} what="link Teams" />;
  if (error) return <Notice tone="danger">{error.message || "Could not load Teams linking."}</Notice>;

  const { teams_enabled, linked, code, minutes, viewer } = data;

  return (
    <div>
      <PageHeader
        title="Link your Teams account"
        lead="So the bot knows which member you are, without the app asking Microsoft who anyone is."
      />

      {!teams_enabled ? (
        <Notice tone="info">
          The Teams bot is not switched on for this deployment. The web form works without it.
        </Notice>
      ) : (
        <div className="card">
          {linked && (
            <Notice tone="info">A Teams account is already linked. Sending a new code replaces it.</Notice>
          )}
          <p className="mb-8">In a one-to-one chat with the bot, send:</p>
          <div className="teams-code-block">
            <pre className="teams-code-pre">link {code}</pre>
            <button type="button" className="btn" onClick={() => handleCopy(code)}>
              {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <div className="meta mt-16">
            <span>
              Links to <strong>{viewer.display_name}</strong>
            </span>
            <span>Expires in {minutes} min</span>
            <span>Works once</span>
          </div>
        </div>
      )}
    </div>
  );
}
