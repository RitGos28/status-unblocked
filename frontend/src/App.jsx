import React, { useState, useEffect } from "react";
import Header from "./components/Header";
import HomePage from "./pages/HomePage";
import SubmitPage from "./pages/SubmitPage";
import DigestsPage from "./pages/DigestsPage";
import DigestDetailPage from "./pages/DigestDetailPage";
import EvidencePage from "./pages/EvidencePage";
import TeamsLinkPage from "./pages/TeamsLinkPage";
import LoginPage from "./pages/LoginPage";
import TeamPage from "./pages/TeamPage";
import MyDataPage from "./pages/MyDataPage";
import ManagerLoginPage from "./pages/ManagerLoginPage";
import ManagerDashboardPage from "./pages/ManagerDashboardPage";

function getRoute() {
  // Support both hash routing and HTML5 path routing
  const hash = window.location.hash.slice(1);
  const path = hash ? (hash.startsWith("/") ? hash : "/" + hash) : window.location.pathname;
  return path || "/";
}

export default function App() {
  const [currentPath, setCurrentPath] = useState(getRoute());

  useEffect(() => {
    const handleLocationChange = () => {
      setCurrentPath(getRoute());
    };

    window.addEventListener("hashchange", handleLocationChange);
    window.addEventListener("popstate", handleLocationChange);
    return () => {
      window.removeEventListener("hashchange", handleLocationChange);
      window.removeEventListener("popstate", handleLocationChange);
    };
  }, []);

  const navigate = (to) => {
    // We update hash so it works across static servers, dev proxy, and direct file access
    if (to.startsWith("/")) {
      window.location.hash = to;
    } else {
      window.location.hash = "/" + to;
    }
    setCurrentPath(to);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Parse path & params
  const [pathname, queryString] = currentPath.split("?");
  const searchParams = new URLSearchParams(queryString || "");

  const renderContent = () => {
    // Route: /login (an old /login/<token> link lands here too)
    if (pathname === "/login" || pathname.startsWith("/login/")) {
      return <LoginPage navigate={navigate} />;
    }

    // The manager portal: its own sign-in, and its own digest and evidence views.
    if (pathname === "/manager/login") {
      return <ManagerLoginPage navigate={navigate} />;
    }
    if (pathname === "/manager") {
      return <ManagerDashboardPage navigate={navigate} />;
    }
    if (pathname.startsWith("/manager/digest/")) {
      const digestId = pathname.replace("/manager/digest/", "");
      return <DigestDetailPage digestId={digestId} navigate={navigate} manager />;
    }
    if (pathname.startsWith("/manager/evidence/")) {
      const itemId = pathname.replace("/manager/evidence/", "");
      return <EvidencePage itemId={itemId} navigate={navigate} manager />;
    }

    // Route: /me/team
    if (pathname === "/me/team") {
      return <TeamPage navigate={navigate} />;
    }

    // Route: /me/data
    if (pathname === "/me/data") {
      return <MyDataPage navigate={navigate} />;
    }

    // Route: /digest/:id
    if (pathname.startsWith("/digest/")) {
      const digestId = pathname.replace("/digest/", "");
      return <DigestDetailPage digestId={digestId} navigate={navigate} />;
    }

    // Route: /evidence/:id
    if (pathname.startsWith("/evidence/")) {
      const itemId = pathname.replace("/evidence/", "");
      return <EvidencePage itemId={itemId} navigate={navigate} />;
    }

    // Route: /submit
    if (pathname === "/submit") {
      return <SubmitPage navigate={navigate} />;
    }

    // Route: /digests
    if (pathname === "/digests") {
      return <DigestsPage navigate={navigate} searchParams={searchParams} />;
    }

    // Route: /me/teams
    if (pathname === "/me/teams") {
      return <TeamsLinkPage navigate={navigate} />;
    }

    // Default / Home
    return <HomePage navigate={navigate} searchParams={searchParams} />;
  };

  return (
    <div className="app-container">
      <Header currentPath={pathname} navigate={navigate} />
      <main>{renderContent()}</main>
    </div>
  );
}
