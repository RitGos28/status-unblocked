import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import {
  ArrowRight,
  CheckCircle2,
  KeyRound,
  Zap,
  Quote,
  ShieldCheck,
  CheckSquare,
  Clock,
  AlertTriangle,
  RefreshCw,
  Calendar,
  AlertCircle,
  Briefcase,
  ChevronRight,
} from "lucide-react";

export default function HomePage({ navigate, searchParams }) {
  const { user } = useAuth();
  const signedOut = searchParams.get("signed_out") === "1";

  const [myTasks, setMyTasks] = useState([]);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [taskFeedback, setTaskFeedback] = useState(null);
  const [updatingTaskId, setUpdatingTaskId] = useState(null);

  const loadMyTasks = async () => {
    if (!user) return;
    try {
      setLoadingTasks(true);
      const res = await api.getMyTasks();
      setMyTasks(res.tasks || []);
    } catch {
      // Non-blocking
    } finally {
      setLoadingTasks(false);
    }
  };

  useEffect(() => {
    if (user) {
      loadMyTasks();
    }
  }, [user]);

  const handleUpdateStatus = async (taskId, newStatus) => {
    try {
      setUpdatingTaskId(taskId);
      const res = await api.updateMyTask(taskId, { status: newStatus });
      setMyTasks((prev) => prev.map((t) => (t.id === taskId ? res.task : t)));
      setTaskFeedback(`Task marked as ${newStatus.replace("_", " ")}.`);
      setTimeout(() => setTaskFeedback(null), 3000);
    } catch (err) {
      setTaskFeedback(err.message || "Failed to update task status.");
      setTimeout(() => setTaskFeedback(null), 4000);
    } finally {
      setUpdatingTaskId(null);
    }
  };

  const getPriorityBadge = (priority) => {
    switch (priority) {
      case "urgent":
        return <span className="badge badge-error">Urgent</span>;
      case "high":
        return <span className="badge badge-warning">High</span>;
      case "low":
        return <span className="badge badge-neutral">Low</span>;
      default:
        return <span className="badge badge-accent">Medium</span>;
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case "completed":
        return (
          <span className="badge badge-success" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <CheckCircle2 size={11} /> Completed
          </span>
        );
      case "in_progress":
        return (
          <span className="badge badge-accent" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <Clock size={11} /> In Progress
          </span>
        );
      case "blocked":
        return (
          <span className="badge badge-error" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <AlertTriangle size={11} /> Blocked
          </span>
        );
      default:
        return (
          <span className="badge badge-neutral" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            Pending
          </span>
        );
    }
  };

  const activeTasksCount = myTasks.filter((t) => t.status !== "completed").length;

  return (
    <div className="stagger">
      <div>
        <h1>Async standups,<br />zero-hallucination.</h1>
        <p className="subtitle">
          Every digest line links back to the exact words its author wrote. No paraphrasing. No ambiguity.
        </p>
      </div>

      {signedOut && !user && (
        <div className="notice-box notice-info" style={{ marginBottom: 0 }}>
          <CheckCircle2 size={17} />
          <span>You have been signed out successfully.</span>
        </div>
      )}

      <div className="card-hero">
        {user ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: "50%",
                  background: "linear-gradient(135deg, var(--accent) 0%, #a78bfa 100%)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 15,
                  fontWeight: 800,
                  color: "white",
                  flexShrink: 0,
                }}
              >
                {user.display_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
              </div>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 1 }}>
                  Welcome back, {user.display_name}!
                </h3>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {user.team_name} · signed in
                </span>
              </div>
            </div>

            <p style={{ color: "var(--text-secondary)", marginBottom: 22, lineHeight: 1.6, fontSize: 14 }}>
              Submit your standup update or catch up on your team's latest verified digests — all claims are extractive and auditable.
            </p>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate("/submit")}
              >
                Submit today's update <ArrowRight size={14} />
              </button>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => navigate("/digests")}
              >
                Read team digests
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => navigate("/manager")}
                style={{ fontSize: 13 }}
              >
                <Briefcase size={14} /> Manager Portal
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <KeyRound size={22} color="var(--accent-bright)" />
              <h3 style={{ fontSize: 17, fontWeight: 700 }}>Sign in with your team code</h3>
            </div>
            <p style={{ color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 18, fontSize: 14 }}>
              Each team has one short code, shared by everyone on it. Enter the code and your name. No passwords, no accounts to create.
            </p>
            <button type="button" className="btn btn-primary" onClick={() => navigate("/login")}>
              Sign in <ArrowRight size={14} />
            </button>
          </div>
        )}
      </div>

      {/* Member's Assigned Tasks Dashboard */}
      {user && (
        <div className="card" style={{ padding: "20px 24px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
              flexWrap: "wrap",
              gap: 10,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: "var(--radius-sm)",
                  background: "var(--accent-subtle)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <CheckSquare size={16} color="var(--accent-bright)" />
              </div>
              <div>
                <h3 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>
                  My Assigned Tasks
                </h3>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  Tasks delegated to you by the manager
                </span>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {activeTasksCount > 0 ? (
                <span className="badge badge-accent">
                  {activeTasksCount} active {activeTasksCount === 1 ? "task" : "tasks"}
                </span>
              ) : myTasks.length > 0 ? (
                <span className="badge badge-success">All tasks completed</span>
              ) : null}

              <button
                type="button"
                className="btn btn-ghost"
                onClick={loadMyTasks}
                disabled={loadingTasks}
                style={{ padding: "6px 8px", fontSize: 12 }}
                title="Refresh tasks"
              >
                <RefreshCw size={13} className={loadingTasks ? "spin" : ""} />
              </button>
            </div>
          </div>

          {taskFeedback && (
            <div
              className="notice-box notice-info"
              style={{ padding: "8px 12px", marginBottom: 14, fontSize: 13 }}
            >
              <CheckCircle2 size={14} />
              <span>{taskFeedback}</span>
            </div>
          )}

          {loadingTasks && myTasks.length === 0 ? (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
              Loading your assigned tasks...
            </div>
          ) : myTasks.length === 0 ? (
            <div
              style={{
                padding: "24px 16px",
                textAlign: "center",
                borderRadius: "var(--radius-md)",
                background: "var(--surface-sunken)",
                border: "1px dashed var(--border-subtle)",
              }}
            >
              <CheckCircle2 size={24} color="var(--accent)" style={{ marginBottom: 8, opacity: 0.8 }} />
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
                No tasks assigned to you
              </div>
              <p style={{ color: "var(--text-muted)", fontSize: 13, margin: 0 }}>
                When your manager assigns a task to you, it will appear here so you can update its status and include it in your daily standup.
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {myTasks.map((task) => (
                <div
                  key={task.id}
                  style={{
                    padding: "14px 16px",
                    borderRadius: "var(--radius-md)",
                    background: "var(--surface-sunken)",
                    border: "1px solid var(--border-subtle)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    transition: "var(--transition-fast)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      justifyContent: "space-between",
                      gap: 12,
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 220 }}>
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: 14,
                          color: task.status === "completed" ? "var(--text-muted)" : "var(--text-primary)",
                          textDecoration: task.status === "completed" ? "line-through" : "none",
                          marginBottom: 4,
                        }}
                      >
                        {task.title}
                      </div>

                      {task.description && (
                        <div
                          style={{
                            fontSize: 13,
                            color: "var(--text-secondary)",
                            lineHeight: 1.5,
                            marginBottom: 6,
                          }}
                        >
                          {task.description}
                        </div>
                      )}

                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        {getStatusBadge(task.status)}
                        {getPriorityBadge(task.priority)}
                        {task.due_date && (
                          <span
                            style={{
                              fontSize: 11,
                              color: "var(--text-muted)",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                            }}
                          >
                            <Calendar size={11} /> Due {task.due_date}
                          </span>
                        )}
                        {task.created_by_name && (
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            Delegated by {task.created_by_name}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Status updater actions */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <select
                        className="select-input"
                        value={task.status}
                        disabled={updatingTaskId === task.id}
                        onChange={(e) => handleUpdateStatus(task.id, e.target.value)}
                        style={{
                          padding: "4px 8px",
                          fontSize: 12,
                          height: 30,
                          minWidth: 120,
                        }}
                      >
                        <option value="pending">Pending</option>
                        <option value="in_progress">In Progress</option>
                        <option value="completed">Completed</option>
                        <option value="blocked">Blocked</option>
                      </select>

                      <button
                        type="button"
                        className="btn btn-outline"
                        style={{ padding: "4px 10px", fontSize: 12, height: 30 }}
                        onClick={() => navigate("/submit")}
                        title="Include in today's standup update"
                      >
                        Standup <ChevronRight size={12} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="feature-grid">
        <div className="feature-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Quote size={15} color="var(--accent-bright)" />
            <div className="feature-label">Extractive Faithfulness</div>
          </div>
          <p className="feature-desc">
            Synthesized lines are verbatim source spans. The summarizer enforces zero-hallucination accuracy on blockers — every claim must trace back to the raw submission.
          </p>
        </div>

        <div className="feature-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <ShieldCheck size={15} color="var(--accent-bright)" />
            <div className="feature-label">Verifiable Citations</div>
          </div>
          <p className="feature-desc">
            Every claim links to its source item evidence with exact character-offset highlighting and tamper-evident audit chain entries.
          </p>
        </div>

        <div className="feature-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Zap size={15} color="var(--accent-bright)" />
            <div className="feature-label">Ecosystem Integration</div>
          </div>
          <p className="feature-desc">
            Full bidirectional support for Microsoft Teams bot ingestion, outbox-drained GitHub issue tracking, and privacy-respecting retention policies.
          </p>
        </div>
      </div>
    </div>
  );
}
