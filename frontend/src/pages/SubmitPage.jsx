import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { Notice, PageHeader, SignInRequired } from "../components/ui";

const FIELDS = [
  {
    id: "progress",
    label: "Progress",
    hint: "what moved since your last update",
    placeholder: "Merged the search index rebuild.",
  },
  {
    id: "blockers",
    label: "Blockers",
    hint: "what is stopping you; this is the part people read",
    placeholder: "Waiting on a design review for the billing page.",
  },
  {
    id: "plan",
    label: "Today",
    hint: "what you are picking up next",
    placeholder: "Write the rollback plan for the payments change.",
  },
];

export default function SubmitPage({ navigate }) {
  const { user } = useAuth();
  const [values, setValues] = useState({ progress: "", blockers: "", plan: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [myTasks, setMyTasks] = useState([]);

  useEffect(() => {
    if (user) {
      api
        .getMyTasks()
        .then((res) => setMyTasks(res.tasks || []))
        .catch(() => {});
    }
  }, [user]);

  if (!user) return <SignInRequired navigate={navigate} what="submit an update" />;

  const set = (id) => (e) => setValues((v) => ({ ...v, [id]: e.target.value }));
  const append = (id, line) =>
    setValues((v) => ({ ...v, [id]: v[id] ? `${v[id]}\n${line}` : line }));

  const hasContent = Object.values(values).join("").trim().length > 0;
  const activeTasks = myTasks.filter((t) => t.status !== "completed");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.submitUpdate(values);
      if (res && res.success) navigate(`/digests?submitted=${res.update_id}`);
    } catch (err) {
      setError(err.message || "Could not submit the update.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Today's update"
        lead="Three short answers. Only what you type here is stored, and only your team can read it."
      />

      {error && <Notice tone="danger">{error}</Notice>}

      {activeTasks.length > 0 && (
        <div className="card card-pad-sm mb-16">
          <div className="eyebrow mb-8">Your open tasks</div>
          <div className="row">
            {activeTasks.map((t) => (
              <span key={t.id} className="badge" style={{ height: 26, gap: 6 }}>
                {t.title}
                <button
                  type="button"
                  className="btn-link small"
                  onClick={() => append("progress", `Progressed on: ${t.title}`)}
                  title="Add to Progress"
                >
                  progress
                </button>
                <button
                  type="button"
                  className="btn-link small"
                  onClick={() => append("plan", `Working on: ${t.title}`)}
                  title="Add to Today"
                >
                  today
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="card">
          {FIELDS.map((f) => (
            <div className="form-group" key={f.id}>
              <label htmlFor={f.id}>
                <span>{f.label}</span>
                <span className="hint">{f.hint}</span>
              </label>
              <textarea
                id={f.id}
                value={values[f.id]}
                onChange={set(f.id)}
                placeholder={f.placeholder}
                disabled={submitting}
              />
            </div>
          ))}

          <div className="form-footer">
            <span className="muted">
              Goes into {user.team_name}'s digest. Submitting again today replaces this update.
            </span>
            <button type="submit" className="btn btn-primary" disabled={submitting || !hasContent}>
              {submitting ? "Submitting…" : "Submit update"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
