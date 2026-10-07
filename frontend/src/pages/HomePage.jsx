import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { Calendar, CheckSquare, RefreshCw } from "lucide-react";
import {
  Avatar,
  EmptyState,
  Notice,
  PriorityBadge,
  StatusBadge,
  StatusSelect,
  STATUS_LABELS,
} from "../components/ui";

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
      // The task list is optional on this page.
    } finally {
      setLoadingTasks(false);
    }
  };

  useEffect(() => {
    if (user) loadMyTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const handleUpdateStatus = async (taskId, newStatus) => {
    try {
      setUpdatingTaskId(taskId);
      const res = await api.updateMyTask(taskId, { status: newStatus });
      setMyTasks((prev) => prev.map((t) => (t.id === taskId ? res.task : t)));
      setTaskFeedback({ tone: "success", text: `Marked as ${STATUS_LABELS[newStatus].toLowerCase()}.` });
      setTimeout(() => setTaskFeedback(null), 3000);
    } catch (err) {
      setTaskFeedback({ tone: "danger", text: err.message || "Could not update the task." });
      setTimeout(() => setTaskFeedback(null), 4000);
    } finally {
      setUpdatingTaskId(null);
    }
  };

  const activeTasks = myTasks.filter((t) => t.status !== "completed");

  if (!user) {
    return (
      <div>
        {signedOut && <Notice tone="success">You are signed out.</Notice>}

        <div className="page-header">
          <div>
            <h1>Standups without the meeting</h1>
            <p className="lead">
              Each person files a short update. Once a day the team gets one digest, and every
              line in it links back to the words it came from.
            </p>
          </div>
        </div>

        <div className="card">
          <h3>Sign in with your team code</h3>
          <p className="muted mt-8 mb-16">
            One code per team, shared by everyone on it. Enter it with your name. There are no
            passwords.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => navigate("/login")}>
            Sign in
          </button>
        </div>

        <div className="features mt-24">
          <div className="feature">
            <h3>Verbatim digests</h3>
            <p>
              Digest lines are quoted from updates, not rewritten. A line that cannot be traced to
              its source is left out and counted.
            </p>
          </div>
          <div className="feature">
            <h3>Evidence for every line</h3>
            <p>
              Each line opens the stored update with the quoted span highlighted. Every view is
              recorded, and the person it concerns can see who looked.
            </p>
          </div>
          <div className="feature">
            <h3>Blockers become issues</h3>
            <p>
              A blocker is filed to GitHub once and updated on each later day it is reported,
              so it has an owner and an age instead of scrolling away.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div className="row">
          <Avatar name={user.display_name} size="lg" />
          <div>
            <h1>{user.display_name}</h1>
            <p className="lead">{user.team_name}</p>
          </div>
        </div>
        <div className="page-header-actions">
          <button type="button" className="btn" onClick={() => navigate("/digests")}>
            Digests
          </button>
          <button type="button" className="btn btn-primary" onClick={() => navigate("/submit")}>
            Submit today's update
          </button>
        </div>
      </div>

      <div className="card card-flush">
        <div className="card-header">
          <div className="row">
            <span className="card-title">Tasks assigned to you</span>
            {activeTasks.length > 0 && <span className="badge badge-accent">{activeTasks.length} open</span>}
            {activeTasks.length === 0 && myTasks.length > 0 && (
              <span className="badge badge-success">All done</span>
            )}
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-icon"
            onClick={loadMyTasks}
            disabled={loadingTasks}
            title="Refresh"
            aria-label="Refresh tasks"
          >
            <RefreshCw size={13} className={loadingTasks ? "spin" : ""} />
          </button>
        </div>

        {taskFeedback && (
          <div style={{ padding: "12px 16px 0" }}>
            <Notice tone={taskFeedback.tone}>{taskFeedback.text}</Notice>
          </div>
        )}

        {loadingTasks && myTasks.length === 0 ? (
          <div className="loading">
            <span className="loading-spinner" /> Loading tasks…
          </div>
        ) : myTasks.length === 0 ? (
          <div style={{ padding: 16 }}>
            <EmptyState icon={CheckSquare} title="No tasks assigned">
              When the manager assigns you a task it appears here, where you can update its status
              and mention it in your standup.
            </EmptyState>
          </div>
        ) : (
          <div className="list">
            {myTasks.map((task) => (
              <div key={task.id} className="task">
                <div className="task-main">
                  <div className={`task-title ${task.status === "completed" ? "done" : ""}`}>
                    {task.title}
                  </div>
                  {task.description && <div className="task-desc">{task.description}</div>}
                  <div className="meta task-meta">
                    <StatusBadge status={task.status} />
                    <PriorityBadge priority={task.priority} />
                    {task.due_date && (
                      <span className="meta-item">
                        <Calendar size={12} /> Due {task.due_date}
                      </span>
                    )}
                    {task.created_by_name && <span>Assigned by {task.created_by_name}</span>}
                  </div>
                </div>
                <div className="task-aside">
                  <StatusSelect
                    value={task.status}
                    disabled={updatingTaskId === task.id}
                    onChange={(v) => handleUpdateStatus(task.id, v)}
                  />
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => navigate("/submit")}
                    title="Mention this task in today's update"
                  >
                    Mention in standup
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
