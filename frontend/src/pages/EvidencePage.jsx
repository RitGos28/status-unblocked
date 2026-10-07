import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { Loading, Notice } from "../components/ui";

const SOURCES = {
  webform: "the web form",
  teams: "Teams",
  cli: "the command line",
  csv: "a spreadsheet import",
};

export default function EvidencePage({ itemId, navigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getEvidence(itemId);
        if (isMounted) setData(res);
      } catch (err) {
        if (isMounted) setError(err.message || "Could not load the evidence.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, [itemId]);

  const back = (
    <button type="button" className="btn btn-ghost btn-sm" onClick={() => window.history.back()}>
      <ArrowLeft size={13} /> Back
    </button>
  );

  if (loading) return <Loading label="Loading evidence…" />;

  if (error) {
    return (
      <div>
        <div className="mb-16">{back}</div>
        <Notice tone="danger">{error}</Notice>
      </div>
    );
  }

  const { expired, quote, before, after, member_name, captured_at, source_kind, permalink, permalink_reason, item } =
    data;
  const captured = new Date(captured_at).toISOString().replace("T", " ").substring(0, 16) + " UTC";

  return (
    <div>
      <div className="mb-16">{back}</div>

      <div className="page-header">
        <div>
          <h1>Source</h1>
          <div className="meta mt-8">
            <span>
              <strong>{member_name}</strong>
            </span>
            <span>{captured}</span>
            <span>via {SOURCES[source_kind] || source_kind}</span>
          </div>
        </div>
      </div>

      {expired ? (
        <div>
          <Notice tone="info">
            The stored update was removed under the team's retention period. The quoted line is kept
            as the digest's record.
          </Notice>
          <h2>Quoted line</h2>
          <pre className="raw-display">
            <mark>{quote}</mark>
          </pre>
        </div>
      ) : (
        <div>
          <h2>As submitted</h2>
          <pre className="raw-display">
            {before}
            <mark>{quote}</mark>
            {after}
          </pre>
          <p className="muted mt-8">
            Characters {item.span_start} to {item.span_end} of the stored update.{" "}
            {permalink ? (
              <a href={permalink} target="_blank" rel="noreferrer">
                Open in {source_kind} <ExternalLink size={11} />
              </a>
            ) : (
              permalink_reason
            )}
          </p>
        </div>
      )}

      <p className="muted mt-24">
        This view was recorded. {member_name} can see who opened their updates on My data.
      </p>
    </div>
  );
}
