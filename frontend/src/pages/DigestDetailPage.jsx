import React, { useState, useEffect } from "react";
import { api, downloads } from "../api/client";
import { ArrowLeft, Download, ExternalLink } from "lucide-react";
import { EmptyState, Loading, Notice, whenUtc } from "../components/ui";

export default function DigestDetailPage({ digestId, navigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showMarkdown, setShowMarkdown] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getDigest(digestId);
        if (isMounted) setData(res);
      } catch (err) {
        if (isMounted) setError(err.message || "Could not load the digest.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, [digestId]);

  const back = (
    <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate("/digests")}>
      <ArrowLeft size={13} /> Digests
    </button>
  );

  if (loading) return <Loading label="Loading digest…" />;

  if (error) {
    return (
      <div>
        <div className="mb-16">{back}</div>
        <Notice tone="danger">{error}</Notice>
      </div>
    );
  }

  const { digest, cycle, team_name, sections } = data;
  const totalClaims = sections.reduce((sum, s) => sum + s.claims.length, 0);

  return (
    <div>
      <div className="mb-16">{back}</div>

      <div className="page-header">
        <div>
          <h1>
            {team_name}, {cycle.local_date}
          </h1>
          <div className="meta mt-8">
            <span>built {whenUtc(digest.generated_at)} UTC</span>
            <span>
              <strong>{totalClaims}</strong> lines
            </span>
            <span className="mono">
              {digest.summarizer_name} {digest.summarizer_version}
            </span>
          </div>
        </div>
        <div className="page-header-actions">
          <a className="btn btn-sm" href={downloads.digestMarkdown(digest.id)} download>
            <Download size={13} /> Markdown
          </a>
          <a className="btn btn-sm" href={downloads.digestCsv(digest.id)} download>
            <Download size={13} /> CSV
          </a>
        </div>
      </div>

      {sections.length === 0 ? (
        <EmptyState title="Nothing to report">No updates were filed for this day.</EmptyState>
      ) : (
        sections.map((section) => (
          <section key={section.kind}>
            <h2>{section.title}</h2>
            {section.hint && <p className="section-hint">{section.hint}</p>}
            <div className="card card-flush">
              <div className="list">
                {section.claims.map((claim) => (
                  <div key={claim.id} className="list-row">
                    <span className="list-who">{claim.member_name}</span>
                    <div className="list-main">
                      <div className="list-text">{claim.text}</div>
                      {claim.rule_explanation && (
                        <span className="list-note">{claim.rule_explanation}</span>
                      )}
                    </div>
                    <div className="list-aside">
                      {claim.issue && (
                        <a
                          className="chip"
                          href={claim.issue.url}
                          target="_blank"
                          rel="noreferrer"
                          title="Tracked as a GitHub issue"
                        >
                          #{claim.issue.number}
                          {claim.issue.age_days ? ` · ${claim.issue.age_days}d` : ""}
                          <ExternalLink size={10} />
                        </a>
                      )}
                      {(claim.citations || []).map((c, i) => (
                        <button
                          key={i}
                          type="button"
                          className="chip chip-accent"
                          title="Open the stored update with these words highlighted"
                          onClick={() => navigate(`/evidence/${c.source_id}`)}
                        >
                          {i === 0 ? "source" : "earlier report"}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        ))
      )}

      {digest.withheld_count > 0 && (
        <div className="mt-24">
          <Notice tone="warning">
            {digest.withheld_count} line{digest.withheld_count === 1 ? "" : "s"} withheld: failed
            source verification, or removed by the author.
          </Notice>
        </div>
      )}
      {digest.truncated_count > 0 && (
        <Notice tone="warning">
          {digest.truncated_count} more line{digest.truncated_count === 1 ? "" : "s"} not shown: a
          section reached its limit.
        </Notice>
      )}

      <div className="form-footer mt-24">
        <span className="muted">Every line is a verbatim quote, checked against its stored source.</span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowMarkdown(!showMarkdown)}>
          {showMarkdown ? "Hide Markdown" : "View as Markdown"}
        </button>
      </div>

      {showMarkdown && (
        <pre className="raw-display mt-16" style={{ maxHeight: 360, overflowY: "auto" }}>
          {digest.body_md}
        </pre>
      )}
    </div>
  );
}
