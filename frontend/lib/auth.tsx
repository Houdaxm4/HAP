"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fetchAuthMe, loginWithPassword, logoutSession } from "./api";

export type AuthState = {
  ready: boolean;
  authenticated: boolean;
  authRequired: boolean;
  username: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [authRequired, setAuthRequired] = useState(true);
  const [username, setUsername] = useState<string | null>(null);

  const applyMe = useCallback(async () => {
    const me = await fetchAuthMe();
    setAuthRequired(me.auth_required);
    setAuthenticated(me.authenticated);
    setUsername(me.username);
    setReady(true);
  }, []);

  useEffect(() => {
    void applyMe().catch(() => {
      setAuthenticated(false);
      setAuthRequired(true);
      setUsername(null);
      setReady(true);
    });
  }, [applyMe]);

  useEffect(() => {
    const onUnauthorized = () => {
      setAuthenticated(false);
      setUsername(null);
    };
    window.addEventListener("hap:unauthorized", onUnauthorized);
    return () => window.removeEventListener("hap:unauthorized", onUnauthorized);
  }, []);

  const login = useCallback(async (user: string, password: string) => {
    await loginWithPassword(user, password);
    await applyMe();
  }, [applyMe]);

  const logout = useCallback(async () => {
    try {
      await logoutSession();
    } finally {
      setAuthenticated(false);
      setUsername(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      ready,
      authenticated,
      authRequired,
      username,
      login,
      logout,
    }),
    [ready, authenticated, authRequired, username, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function isAuthStorageClean(): boolean {
  if (typeof window === "undefined") {
    return true;
  }
  try {
    const keys = Object.keys(window.localStorage);
    return keys.every(
      (key) =>
        !key.toLowerCase().includes("password") &&
        !key.toLowerCase().includes("hap_session") &&
        key !== "hap_auth",
    );
  } catch {
    return true;
  }
}
