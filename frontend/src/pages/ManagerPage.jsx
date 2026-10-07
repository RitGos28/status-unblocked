import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import {
  Briefcase,
  CheckCircle2,
  Clock,
  AlertCircle,
  Plus,
  Users,
  UserPlus,
  FileText,
  KeyRound,
  Copy,
  Check,
  Trash2,
  Sparkles,
  TrendingUp,
  RefreshCw,
  Calendar,
  AlertTriangle,
} from "lucide-react";

export default function ManagerPage({ navigate }) {
  const { user } = useAuth();
  const [tasks, setTasks] = useState([]);
  const [teamInfo, setTeamInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("tasks"); // "tasks" | "members" | "summary" | "teamcode"
  const [statusFilter, setStatusFilter] = useState("all");

  // Summary state
  const [summaryScope, setSummaryScope] = useState("daily"); // "daily" | "project"
  const [summaryData, setSummaryData] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [summaryCopied, setSummaryCopied] = useState(false);

  // New Task form state
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [taskAssignee, setTaskAssignee] = useState("");
  const [taskPriority, setTaskPriority] = useState("medium");
  const [taskDueDate, setTaskDueDate] = useState("");
  const [savingTask, setSavingTask] = useState(false);

  // Add Member form state
  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberTz, setNewMemberTz] = useState("Asia/Kolkata");
  const [savingMember, setSavingMember] = useState(false);

  // Team Code state
  const [customCodeInput, setCustomCodeInput] = useState("");
  const [savingCode, setSavingCode] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);

  // General messages
  const [feedback, setFeedback] = useState(null); // { type: 'success' | 'error', message: '' }

  const loadData = async () => {
    try {
      setLoading(true);
      const [tasksRes, teamRes] = await Promise.all([
        api.getManagerTasks(),
        api.getTeam(),
      ]);
      setTasks(tasksRes.tasks || []);
      setTeamInfo(teamRes.team || null);
    } catch (err) {
      setFeedback({ type: "error", message: err.message || "Failed to load manager data." });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) {
      loadData();
    }
  }, [user]);

  // Load summary whenever user switches to summary tab or toggles scope
  useEffect(() => {
    if (activeTab === "summary" && user) {
      loadSummary(summaryScope);
    }
  }, [activeTab, summaryScope]);

  const loadSummary = async (scope) => {
    try {
      setLoadingSummary(true);
      const res = await api.getManagerSummary(scope);
      setSummaryData(res);
    } catch (err) {
      setFeedback({ type: "error", message: err.message || "Failed to generate summary." });
    } finally {
      setLoadingSummary(false);
    }
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    try {
      setSavingTask(true);
      const res = await api.createManagerTask({
        title: taskTitle.trim(),
        description: taskDescription.trim(),
        assigned_to_id: taskAssignee || null,
        priority: taskPriority,
        due_date: taskDueDate || null,
      });
      setTasks((prev) => [res.task, ...prev]);
      setTaskTitle("");
      setTaskDescription("");
      setTaskAssignee("");
      setTaskDueDate("");
      setShowTaskModal(false);
      setFeedback({ type: "success", message: `Task "${res.task.title}" created successfully.` });
    } catch (err) {
      setFeedback({ type: "error", message: err.message || "Failed to create task." });
    } finally {
      setSavingTask(false);
    }
  };

  const handleUpdateStatus = async (taskId, newStatus) => {
    try {
      const res = await api.updateManagerTask(taskId, { status: newStatus });
      setTasks((prev) => prev.map((t) => (t.id === taskId ? res.task : t)));
    } catch (err) {
      setFeedback({ type: "error", message: err.message || "Failed to update task status." });
    }
  };

  const handleDeleteTask = async (taskId) => {
    if (!window.confirm("Are you sure you want to delete this task?")) return;
    try {
      await api.deleteManagerTask(taskId);
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
      setFeedback({ type: "success", message: "Task deleted." });
    } catch (err) {
      setFeedback({ type: "error", message: err.message || "Failed to delete task." });
    }
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!newMemberName.trim()) return;
    try {
      setSavingMember(true);
      const res = await api.addManagerMember({
        name: newMemberName.trim(),
        tz: newMemberTz.trim() || "UTC",
      });
      setNewMemberName("");
      // Reload team info to reflect new member in team list and dropdowns
      const teamRes = await api.getTeam();
      setTeamInfo(teamRes.team || null);
      setFeedback({
        type: "success",
        message: `Member "${res.member.display_name}" added to the team! Visible on Team page and assignments.`,
      });
    } catch (err) {
      setFeedback({ type: "error", message: err.message || "Failed to add member." });
    } finally {
      setSavingMember(false);
    }
  };

  const handleUpdateTeamCode = async (customCode) => {
    try {
      setSavingCode(true);
      const res = await api.updateTeamCode(customCode);
      setTeamInfo((prev) => (prev ? { ...prev, join_code: res.join_code } : prev));
      setCustomCodeInput("");
      setFeedback({
        type: "success",
        message: `Team code updated to ${res.join_code}. Members can now use this code on any deployment!`,
      });
    } catch (err) {
      setFeedback({ type: "error", message: err.message || "Failed to update team code." });
    } finally {
      setSavingCode(false);
    }
  };

  const copyToClipboard = (text, setCopiedFn) => {
    navigator.clipboard.writeText(text);
    setCopiedFn(true);
    setTimeout(() => setCopiedFn(false), 2000);
  };

  const copySummaryMarkdown = () => {
    if (!summaryData) return;
    const lines = [
      `# ${summaryData.headline}`,
      `Generated: ${new Date(summaryData.generated_at).toLocaleString()}`,
      "",
      `## Key Stats`,
      `- Total Tasks: ${summaryData.stats.total_tasks}`,
      `- Completed: ${summaryData.stats.completed} (${summaryData.stats.completion_rate}%)`,
      `- In Progress: ${summaryData.stats.in_progress}`,
      `- Blocked: ${summaryData.stats.blocked}`,
      `- Standup Updates: ${summaryData.stats.updates_submitted}`,
      "",
      `## Key Accomplishments & Completed Tasks`,
      ...(summaryData.completed_tasks.length
        ? summaryData.completed_tasks.map(
            (t) => `- [x] ${t.title} ${t.assigned_to_name ? `(@${t.assigned_to_name})` : ""}`
          )
        : ["- None recorded"]),
      "",
      `## In-Progress Focus`,
      ...(summaryData.in_progress_tasks.length
        ? summaryData.in_progress_tasks.map(
            (t) => `- [ ] ${t.title} ${t.assigned_to_name ? `(@${t.assigned_to_name})` : ""}`
          )
        : ["- None currently in progress"]),
      "",
      `## Blockers & Risks`,
      ...(summaryData.standup_blockers.length
        ? summaryData.standup_blockers.map((b) => `- ⚠️ ${b.member_name}: ${b.blocker}`)
        : ["- No blockers reported"]),
      "",
      `## Team Member Breakdown`,
      ...summaryData.member_breakdowns.map(
        (m) =>
          `### ${m.member_name}\n- Tasks: ${m.tasks_completed}/${m.tasks_total} completed\n- Progress: ${
            m.latest_progress || "No update"
          }\n- Plan: ${m.latest_plan || "None"}`
      ),
    ];
    copyToClipboard(lines.join("\n"), setSummaryCopied);
  };

  if (!user) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "40px 30px" }}>
        <Briefcase size={32} color="var(--text-muted)" style={{ marginBottom: 14 }} />
        <h3 style={{ marginBottom: 8 }}>Sign In Required</h3>
        <p className="muted" style={{ marginBottom: 20 }}>
          Please sign in with your team code to access the manager dashboard.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/login")}>
          Sign in
        </button>
      </div>
    );
  }

  const filteredTasks = tasks.filter((t) => {
    if (statusFilter === "all") return true;
    return t.status === statusFilter;
  });

  const memberNames = teamInfo?.members || [];

  return (
    <div className="stagger">
      {/* Header */}
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1>Manager Dashboard</h1>
            <span className="badge badge-primary">{teamInfo?.name || user.team_name}</span>
          </div>
          <p className="subtitle" style={{ marginBottom: 0 }}>
            Assign tasks to team members, track daily deliverables, and generate end-of-day project summaries.
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setShowTaskModal(true)}
          >
            <Plus size={15} /> Assign Task
          </button>
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => {
              setActiveTab("summary");
              loadSummary(summaryScope);
            }}
          >
            <Sparkles size={15} color="var(--accent-bright)" /> Generate Summary
          </button>
        </div>
      </div>

      {/* Global feedback message */}
      {feedback && (
        <div
          className={`notice-box ${feedback.type === "error" ? "notice-warn" : "notice-info"}`}
          style={{ marginBottom: 20 }}
        >
          {feedback.type === "error" ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
          <span>{feedback.message}</span>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ marginLeft: "auto", padding: "2px 8px", fontSize: 12 }}
            onClick={() => setFeedback(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Nav Tabs */}
      <div className="tab-pill-group" style={{ marginBottom: 24 }}>
        <button
          type="button"
          className={`tab-pill ${activeTab === "tasks" ? "active" : ""}`}
          onClick={() => setActiveTab("tasks")}
        >
          <Briefcase size={14} />
          <span>Team Tasks ({tasks.length})</span>
        </button>
        <button
          type="button"
          className={`tab-pill ${activeTab === "summary" ? "active" : ""}`}
          onClick={() => setActiveTab("summary")}
        >
          <FileText size={14} />
          <span>Summarize Work</span>
        </button>
        <button
          type="button"
          className={`tab-pill ${activeTab === "members" ? "active" : ""}`}
          onClick={() => setActiveTab("members")}
        >
          <Users size={14} />
          <span>Team Members ({memberNames.length})</span>
        </button>
        <button
          type="button"
          className={`tab-pill ${activeTab === "teamcode" ? "active" : ""}`}
          onClick={() => setActiveTab("teamcode")}
        >
          <KeyRound size={14} />
          <span>Team Code & Deployment</span>
        </button>
      </div>

      {/* ================================================================= */}
      {/* TAB 1: TEAM TASKS */}
      {/* ================================================================= */}
      {activeTab === "tasks" && (
        <div>
          {/* Quick Stats Banner */}
          <div className="stat-cards-grid" style={{ marginBottom: 24 }}>
            <div className="stat-card">
              <span className="stat-card-label">Total Tasks</span>
              <span className="stat-card-value">{tasks.length}</span>
            </div>
            <div className="stat-card">
              <span className="stat-card-label">In Progress</span>
              <span className="stat-card-value" style={{ color: "var(--accent-bright)" }}>
                {tasks.filter((t) => t.status === "in_progress").length}
              </span>
            </div>
            <div className="stat-card">
              <span className="stat-card-label">Completed</span>
              <span className="stat-card-value" style={{ color: "var(--success)" }}>
                {tasks.filter((t) => t.status === "completed").length}
              </span>
            </div>
            <div className="stat-card">
              <span className="stat-card-label">Blocked</span>
              <span className="stat-card-value" style={{ color: "var(--warn)" }}>
                {tasks.filter((t) => t.status === "blocked").length}
              </span>
            </div>
          </div>

          {/* Filter Bar */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 12,
              marginBottom: 16,
            }}
          >
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {["all", "pending", "in_progress", "completed", "blocked"].map((st) => (
                <button
                  key={st}
                  type="button"
                  className={`btn ${statusFilter === st ? "btn-primary" : "btn-outline"}`}
                  style={{ fontSize: 12, padding: "5px 12px", textTransform: "capitalize" }}
                  onClick={() => setStatusFilter(st)}
                >
                  {st.replace("_", " ")}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn btn-outline"
              style={{ fontSize: 13, padding: "6px 12px" }}
              onClick={loadData}
              title="Refresh tasks"
            >
              <RefreshCw size={13} /> Refresh
            </button>
          </div>

          {loading ? (
            <div style={{ textAlign: "center", padding: 50 }}>
              <span className="loading-spinner" />
            </div>
          ) : filteredTasks.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: "50px 20px" }}>
              <Briefcase size={32} color="var(--text-muted)" style={{ marginBottom: 12 }} />
              <h3>No tasks found</h3>
              <p className="muted" style={{ marginBottom: 16 }}>
                {statusFilter === "all"
                  ? "Get started by assigning a task to a team member."
                  : `No tasks currently marked as "${statusFilter.replace("_", " ")}".`}
              </p>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setShowTaskModal(true)}
              >
                <Plus size={14} /> Assign New Task
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {filteredTasks.map((task) => (
                <div key={task.id} className="card card-elevated" style={{ padding: "18px 20px" }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      justifyContent: "space-between",
                      gap: 14,
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 260 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                        <span
                          className={`badge ${
                            task.priority === "urgent"
                              ? "badge-warn"
                              : task.priority === "high"
                              ? "badge-amber"
                              : task.priority === "medium"
                              ? "badge-primary"
                              : "badge-neutral"
                          }`}
                        >
                          {task.priority.toUpperCase()}
                        </span>
                        <h3 style={{ fontSize: 16, margin: 0 }}>{task.title}</h3>
                      </div>
                      {task.description && (
                        <p className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
                          {task.description}
                        </p>
                      )}
                      <div className="stat-row" style={{ marginTop: 8 }}>
                        <div className="stat-chip">
                          <Users size={12} />
                          <span>
                            Assigned to:{" "}
                            <strong>{task.assigned_to_name || "Unassigned"}</strong>
                          </span>
                        </div>
                        {task.due_date && (
                          <div className="stat-chip">
                            <Calendar size={12} />
                            <span>Due: {task.due_date}</span>
                          </div>
                        )}
                        {task.completed_at && (
                          <div className="stat-chip" style={{ color: "var(--success)" }}>
                            <CheckCircle2 size={12} />
                            <span>Done {new Date(task.completed_at).toLocaleDateString()}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Quick Status Control */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <select
                        value={task.status}
                        onChange={(e) => handleUpdateStatus(task.id, e.target.value)}
                        className="select-status"
                        style={{
                          background:
                            task.status === "completed"
                              ? "var(--success-bg)"
                              : task.status === "blocked"
                              ? "var(--warn-bg)"
                              : task.status === "in_progress"
                              ? "var(--accent-dim)"
                              : "var(--bg-surface)",
                          color:
                            task.status === "completed"
                              ? "var(--success)"
                              : task.status === "blocked"
                              ? "var(--warn)"
                              : task.status === "in_progress"
                              ? "var(--accent-bright)"
                              : "var(--text-secondary)",
                          borderColor: "var(--border-subtle)",
                          fontSize: 13,
                          padding: "6px 12px",
                          borderRadius: "var(--r-md)",
                          fontWeight: 500,
                          cursor: "pointer",
                        }}
                      >
                        <option value="pending">⏳ Pending</option>
                        <option value="in_progress">⚡ In Progress</option>
                        <option value="completed">✓ Completed</option>
                        <option value="blocked">⚠️ Blocked</option>
                      </select>

                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => handleDeleteTask(task.id)}
                        title="Delete task"
                        style={{ padding: "6px 8px", color: "var(--text-muted)" }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ================================================================= */}
      {/* TAB 2: SUMMARIZE WORK FEATURE */}
      {/* ================================================================= */}
      {activeTab === "summary" && (
        <div className="stagger">
          <div className="card card-elevated" style={{ padding: "26px 26px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 14,
                marginBottom: 20,
              }}
            >
              <div>
                <h2 style={{ fontSize: 18, marginBottom: 4 }}>End-of-Day & Project Summary</h2>
                <p className="muted" style={{ fontSize: 13, margin: 0 }}>
                  Automated synthesis of completed tasks, ongoing deliverables, blockers, and standup contributions.
                </p>
              </div>

              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <div className="tab-pill-group" style={{ margin: 0 }}>
                  <button
                    type="button"
                    className={`tab-pill ${summaryScope === "daily" ? "active" : ""}`}
                    onClick={() => setSummaryScope("daily")}
                  >
                    Daily
                  </button>
                  <button
                    type="button"
                    className={`tab-pill ${summaryScope === "project" ? "active" : ""}`}
                    onClick={() => setSummaryScope("project")}
                  >
                    Project-Wide
                  </button>
                </div>

                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={copySummaryMarkdown}
                  disabled={!summaryData}
                  style={{ fontSize: 13 }}
                >
                  {summaryCopied ? <Check size={14} /> : <Copy size={14} />}
                  {summaryCopied ? "Copied" : "Copy Report"}
                </button>
              </div>
            </div>

            {loadingSummary ? (
              <div style={{ textAlign: "center", padding: "60px 20px" }}>
                <span className="loading-spinner" />
                <p className="muted" style={{ marginTop: 14 }}>
                  Synthesizing deliverables, standup reports, and blockers…
                </p>
              </div>
            ) : !summaryData ? (
              <p className="muted">No summary data available.</p>
            ) : (
              <div>
                {/* Executive Headline Banner */}
                <div
                  style={{
                    padding: "16px 20px",
                    background: "var(--accent-dim)",
                    border: "1px solid var(--accent-border)",
                    borderRadius: "var(--r-md)",
                    marginBottom: 24,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Sparkles size={18} color="var(--accent-bright)" />
                    <strong style={{ fontSize: 15, color: "var(--text-primary)" }}>
                      {summaryData.headline}
                    </strong>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
                    Generated on {new Date(summaryData.generated_at).toLocaleString()}
                  </div>
                </div>

                {/* Metrics Breakdown */}
                <div className="stat-cards-grid" style={{ marginBottom: 24 }}>
                  <div className="stat-card">
                    <span className="stat-card-label">Completion Rate</span>
                    <span className="stat-card-value" style={{ color: "var(--success)" }}>
                      {summaryData.stats.completion_rate}%
                    </span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-card-label">Completed Tasks</span>
                    <span className="stat-card-value">{summaryData.stats.completed}</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-card-label">In Progress</span>
                    <span className="stat-card-value" style={{ color: "var(--accent-bright)" }}>
                      {summaryData.stats.in_progress}
                    </span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-card-label">Identified Blockers</span>
                    <span
                      className="stat-card-value"
                      style={{
                        color:
                          summaryData.stats.blocked + summaryData.standup_blockers.length > 0
                            ? "var(--warn)"
                            : "var(--text-secondary)",
                      }}
                    >
                      {summaryData.stats.blocked + summaryData.standup_blockers.length}
                    </span>
                  </div>
                </div>

                {/* Accomplishments Section */}
                <h3 style={{ fontSize: 15, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
                  <CheckCircle2 size={16} color="var(--success)" /> Key Accomplishments & Finished Work
                </h3>
                <div className="card" style={{ padding: "14px 18px", marginBottom: 20 }}>
                  {summaryData.completed_tasks.length === 0 ? (
                    <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                      No tasks marked completed yet for this period.
                    </p>
                  ) : (
                    <ul style={{ paddingLeft: 20, margin: 0, display: "flex", flexDirection: "column", gap: 6 }}>
                      {summaryData.completed_tasks.map((t) => (
                        <li key={t.id} style={{ fontSize: 14 }}>
                          <strong>{t.title}</strong>
                          {t.assigned_to_name && (
                            <span className="muted" style={{ marginLeft: 6 }}>
                              — completed by {t.assigned_to_name}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Blockers & Risks Section */}
                <h3 style={{ fontSize: 15, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
                  <AlertCircle size={16} color="var(--warn)" /> Active Blockers & Impediments
                </h3>
                <div className="card" style={{ padding: "14px 18px", marginBottom: 20 }}>
                  {summaryData.standup_blockers.length === 0 && summaryData.blocked_tasks.length === 0 ? (
                    <p className="muted" style={{ margin: 0, fontSize: 13, color: "var(--success)" }}>
                      ✓ All clear! No open blockers reported.
                    </p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {summaryData.standup_blockers.map((b, i) => (
                        <div key={i} className="notice-box notice-warn" style={{ padding: "8px 12px" }}>
                          <AlertTriangle size={14} />
                          <span>
                            <strong>{b.member_name}:</strong> {b.blocker}
                          </span>
                        </div>
                      ))}
                      {summaryData.blocked_tasks.map((t) => (
                        <div key={t.id} className="notice-box notice-warn" style={{ padding: "8px 12px" }}>
                          <AlertTriangle size={14} />
                          <span>
                            <strong>Task Blocked:</strong> {t.title} ({t.assigned_to_name || "Unassigned"})
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Team Contributions Breakdown */}
                <h3 style={{ fontSize: 15, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
                  <Users size={16} color="var(--accent-bright)" /> Team Member Contribution Breakdown
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
                  {summaryData.member_breakdowns.map((m) => (
                    <div key={m.member_id} className="card card-elevated" style={{ padding: "16px 18px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <strong style={{ fontSize: 15 }}>{m.member_name}</strong>
                        <span className="badge badge-neutral" style={{ fontSize: 11 }}>
                          {m.tasks_completed}/{m.tasks_total} Tasks Done
                        </span>
                      </div>
                      {m.latest_progress && (
                        <p style={{ fontSize: 13, marginBottom: 6, color: "var(--text-secondary)" }}>
                          <strong>Progress:</strong> {m.latest_progress}
                        </p>
                      )}
                      {m.latest_blockers && (
                        <p style={{ fontSize: 13, marginBottom: 6, color: "var(--warn)" }}>
                          <strong>Blocker:</strong> {m.latest_blockers}
                        </p>
                      )}
                      {m.latest_plan && (
                        <p style={{ fontSize: 13, margin: 0, color: "var(--text-muted)" }}>
                          <strong>Plan:</strong> {m.latest_plan}
                        </p>
                      )}
                      {!m.latest_progress && !m.latest_plan && (
                        <p className="muted" style={{ fontSize: 12, margin: 0 }}>
                          No standup update submitted yet for this cycle.
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ================================================================= */}
      {/* TAB 3: TEAM MEMBERS */}
      {/* ================================================================= */}
      {activeTab === "members" && (
        <div className="stagger">
          {/* Add Member Card */}
          <div className="card card-elevated" style={{ padding: "24px 26px", marginBottom: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <UserPlus size={18} color="var(--accent-bright)" />
              <h3 style={{ fontSize: 17, margin: 0 }}>Add Team Member</h3>
            </div>
            <p className="muted" style={{ fontSize: 13, marginBottom: 20 }}>
              Add a new teammate directly. They will immediately appear on the Team page, in task assignment dropdowns, and can sign in with the team code.
            </p>

            <form onSubmit={handleAddMember}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                <div className="form-group" style={{ margin: 0 }}>
                  <label htmlFor="member_name">
                    <span>Full Name</span>
                    <span className="hint">e.g. Pooja Hegde</span>
                  </label>
                  <input
                    id="member_name"
                    type="text"
                    value={newMemberName}
                    onChange={(e) => setNewMemberName(e.target.value)}
                    placeholder="e.g. Rahul Deshmukh"
                    required
                    disabled={savingMember}
                  />
                </div>
                <div className="form-group" style={{ margin: 0 }}>
                  <label htmlFor="member_tz">
                    <span>Timezone</span>
                    <span className="hint">for standup cycles</span>
                  </label>
                  <input
                    id="member_tz"
                    type="text"
                    value={newMemberTz}
                    onChange={(e) => setNewMemberTz(e.target.value)}
                    placeholder="e.g. Asia/Kolkata or UTC"
                    disabled={savingMember}
                  />
                </div>
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={savingMember || !newMemberName.trim()}
              >
                {savingMember ? "Adding member…" : "Add to Team"}
              </button>
            </form>
          </div>

          {/* Current Team Members Directory */}
          <h2 style={{ fontSize: 17, marginBottom: 12 }}>Current Team Roster</h2>
          <div className="card card-elevated" style={{ padding: "8px 24px" }}>
            {memberNames.map((name) => (
              <div key={name} className="claim-row">
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div className="user-avatar" style={{ width: 28, height: 28, fontSize: 12 }}>
                    {name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
                  </div>
                  <span className="claim-who" style={{ fontSize: 14 }}>{name}</span>
                </div>
                <div className="claim-content">
                  <span className="muted" style={{ fontSize: 12 }}>
                    {name === user.display_name ? "(You)" : "Active Teammate"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ================================================================= */}
      {/* TAB 4: TEAM CODE & DEPLOYMENT SYNC */}
      {/* ================================================================= */}
      {activeTab === "teamcode" && (
        <div className="stagger">
          <div className="card card-elevated" style={{ padding: "26px 26px", marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <KeyRound size={20} color="var(--accent-bright)" />
              <h3 style={{ fontSize: 17, margin: 0 }}>Team Sign-in & Sync Code</h3>
            </div>
            <p className="muted" style={{ fontSize: 13, marginBottom: 20 }}>
              The code every member of {teamInfo?.name || "your team"} uses to sign in or join. No passwords required.
            </p>

            <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", marginBottom: 18 }}>
              <code className="code-inline" style={{ fontSize: 24, letterSpacing: "0.08em", padding: "8px 16px" }}>
                {teamInfo?.join_code || "..."}
              </code>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => copyToClipboard(teamInfo?.join_code || "", setCodeCopied)}
              >
                {codeCopied ? <Check size={14} color="var(--success)" /> : <Copy size={14} />}
                {codeCopied ? "Copied" : "Copy Code"}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => handleUpdateTeamCode(null)}
                disabled={savingCode}
                title="Rotate to a new random code"
              >
                <RefreshCw size={14} /> Regenerate Random Code
              </button>
            </div>

            {/* Sync Local with Deployed Feature */}
            <div
              style={{
                marginTop: 24,
                paddingTop: 20,
                borderTop: "1px solid var(--border-subtle)",
              }}
            >
              <h4 style={{ fontSize: 15, marginBottom: 6 }}>Sync Local and Deployed Team Code</h4>
              <p className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
                If you generated a team code on your local PC (e.g. <code>CORE-7K3MQ</code>) and want the deployed website to accept that exact same code, enter it below to synchronize them:
              </p>

              <div style={{ display: "flex", gap: 10, maxWidth: 440 }}>
                <input
                  type="text"
                  value={customCodeInput}
                  onChange={(e) => setCustomCodeInput(e.target.value)}
                  placeholder="e.g. CORE-7K3MQ"
                  style={{ textTransform: "uppercase" }}
                  disabled={savingCode}
                />
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => handleUpdateTeamCode(customCodeInput)}
                  disabled={savingCode || !customCodeInput.trim()}
                  style={{ flexShrink: 0 }}
                >
                  {savingCode ? "Saving…" : "Save Custom Code"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ================================================================= */}
      {/* MODAL: ASSIGN TASK */}
      {/* ================================================================= */}
      {showTaskModal && (
        <div className="modal-backdrop" onClick={() => setShowTaskModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Briefcase size={18} color="var(--accent-bright)" />
                <h3 style={{ fontSize: 17, margin: 0 }}>Assign Team Task</h3>
              </div>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setShowTaskModal(false)}
                style={{ padding: "4px 8px" }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateTask}>
              <div className="form-group">
                <label htmlFor="task_title">
                  <span>Task Title</span>
                  <span className="hint">what needs to be accomplished</span>
                </label>
                <input
                  id="task_title"
                  type="text"
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder="e.g. Fix database connection pooling on staging"
                  required
                  disabled={savingTask}
                />
              </div>

              <div className="form-group">
                <label htmlFor="task_desc">
                  <span>Description & Context</span>
                  <span className="hint">optional background or links</span>
                </label>
                <textarea
                  id="task_desc"
                  rows={3}
                  value={taskDescription}
                  onChange={(e) => setTaskDescription(e.target.value)}
                  placeholder="Details, requirements, or PR references…"
                  disabled={savingTask}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div className="form-group">
                  <label htmlFor="task_assignee">Assign to Member</label>
                  <select
                    id="task_assignee"
                    value={taskAssignee}
                    onChange={(e) => setTaskAssignee(e.target.value)}
                    disabled={savingTask}
                    className="select-status"
                    style={{ width: "100%", padding: "9px 12px", background: "var(--bg-surface)" }}
                  >
                    <option value="">Unassigned</option>
                    {tasksResAssignees(tasks, teamInfo).map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.display_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="task_priority">Priority</label>
                  <select
                    id="task_priority"
                    value={taskPriority}
                    onChange={(e) => setTaskPriority(e.target.value)}
                    disabled={savingTask}
                    className="select-status"
                    style={{ width: "100%", padding: "9px 12px", background: "var(--bg-surface)" }}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="task_due">Due Date</label>
                <input
                  id="task_due"
                  type="date"
                  value={taskDueDate}
                  onChange={(e) => setTaskDueDate(e.target.value)}
                  disabled={savingTask}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 20 }}>
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => setShowTaskModal(false)}
                  disabled={savingTask}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={savingTask || !taskTitle.trim()}
                >
                  {savingTask ? "Assigning…" : "Create & Assign Task"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// Helper to deduce member IDs for dropdown
function tasksResAssignees(tasks, teamInfo) {
  if (teamInfo?.members_detailed?.length) {
    return teamInfo.members_detailed;
  }
  const map = new Map();
  // Fallback: deduce from tasks
  tasks.forEach((t) => {
    if (t.assigned_to_id && t.assigned_to_name) {
      map.set(t.assigned_to_id, { id: t.assigned_to_id, display_name: t.assigned_to_name });
    }
  });
  return Array.from(map.values());
}
