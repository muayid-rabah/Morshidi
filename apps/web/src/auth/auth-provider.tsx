"use client";

import type { Session, User } from "@supabase/supabase-js";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { createClient } from "@/lib/supabase/client";

type AuthStatus =
  | "loading"
  | "authenticated"
  | "unauthenticated"
  | "configuration_error";

interface AuthResult<T> {
  data: T;
  error: { message: string } | null;
}

export interface AuthClientPort {
  auth: {
    getSession(): Promise<AuthResult<{ session: Session | null }>>;
    refreshSession(): Promise<AuthResult<{ session: Session | null }>>;
    signInWithPassword(credentials: {
      email: string;
      password: string;
    }): Promise<AuthResult<{ session: Session | null; user: User | null }>>;
    signOut(options?: { scope?: "global" | "local" | "others" }): Promise<{
      error: { message: string } | null;
    }>;
    onAuthStateChange(
      callback: (event: string, session: Session | null) => void,
    ): { data: { subscription: { unsubscribe(): void } } };
  };
}

export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  signIn(email: string, password: string): Promise<{ ok: boolean }>;
  signOut(): Promise<{ ok: boolean }>;
  getAccessToken(): Promise<string | null>;
  refreshAccessToken(): Promise<string | null>;
  invalidateSession(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function resolveSession(
  session: Session | null,
): Pick<AuthContextValue, "status" | "user"> {
  return session
    ? { status: "authenticated", user: session.user }
    : { status: "unauthenticated", user: null };
}

export function AuthProvider({
  children,
  client: injectedClient,
}: {
  children: ReactNode;
  client?: AuthClientPort;
}) {
  const [client] = useState<AuthClientPort | null>(() => {
    if (injectedClient) return injectedClient;
    try {
      return createClient() as unknown as AuthClientPort;
    } catch {
      return null;
    }
  });
  const [status, setStatus] = useState<AuthStatus>(
    client ? "loading" : "configuration_error",
  );
  const [user, setUser] = useState<User | null>(null);

  const applySession = useCallback((session: Session | null) => {
    const next = resolveSession(session);
    setStatus(next.status);
    setUser(next.user);
  }, []);

  useEffect(() => {
    if (!client) return;
    let active = true;
    void client.auth.getSession().then(({ data, error }) => {
      if (!active) return;
      if (error) applySession(null);
      else applySession(data.session);
    });
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      if (active) applySession(session);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [applySession, client]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      if (!client) return { ok: false };
      const { data, error } = await client.auth.signInWithPassword({ email, password });
      if (error || !data.session) {
        applySession(null);
        return { ok: false };
      }
      applySession(data.session);
      return { ok: true };
    },
    [applySession, client],
  );

  const signOut = useCallback(async () => {
    if (!client) return { ok: false };
    const { error } = await client.auth.signOut();
    if (error) return { ok: false };
    applySession(null);
    return { ok: true };
  }, [applySession, client]);

  const getAccessToken = useCallback(async () => {
    if (!client) return null;
    const { data, error } = await client.auth.getSession();
    if (error || !data.session) {
      applySession(null);
      return null;
    }
    applySession(data.session);
    return data.session.access_token;
  }, [applySession, client]);

  const refreshAccessToken = useCallback(async () => {
    if (!client) return null;
    const { data, error } = await client.auth.refreshSession();
    if (error || !data.session) {
      applySession(null);
      return null;
    }
    applySession(data.session);
    return data.session.access_token;
  }, [applySession, client]);

  const invalidateSession = useCallback(async () => {
    if (client) await client.auth.signOut({ scope: "local" });
    applySession(null);
  }, [applySession, client]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      isLoading: status === "loading",
      isAuthenticated: status === "authenticated",
      signIn,
      signOut,
      getAccessToken,
      refreshAccessToken,
      invalidateSession,
    }),
    [
      getAccessToken,
      invalidateSession,
      refreshAccessToken,
      signIn,
      signOut,
      status,
      user,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
