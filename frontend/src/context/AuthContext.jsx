import React, { createContext, useContext, useState, useEffect } from "react";
import { api } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const checkAuth = async () => {
    try {
      setLoading(true);
      const data = await api.getCurrentUser();
      if (data && data.authenticated) {
        setUser(data.member);
      } else {
        setUser(null);
      }
    } catch (err) {
      console.error("Auth check failed:", err);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  // Sign in with the team's shared code and the member's name.
  const login = async (teamCode, name) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.login(teamCode, name);
      if (res.success && res.member) {
        setUser(res.member);
        return res.member;
      }
      throw new Error("That team code and name do not match anyone.");
    } catch (err) {
      setError(err.message || "That team code and name do not match anyone.");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch (err) {
      console.error("Logout error:", err);
    } finally {
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, error, checkAuth, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
