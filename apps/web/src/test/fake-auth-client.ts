import type { Session, User } from "@supabase/supabase-js";

import type { AuthClientPort } from "@/auth/auth-provider";

export const fakeUser = {
  id: "user-1",
  email: "student@example.com",
} as User;

export function fakeSession(token = "current-access-token"): Session {
  return {
    access_token: token,
    refresh_token: "private-refresh-token",
    expires_in: 3600,
    expires_at: 9999999999,
    token_type: "bearer",
    user: fakeUser,
  };
}

export class FakeAuthClient implements AuthClientPort {
  current: Session | null;
  signInError = false;
  signOutError = false;
  getSessionCalls = 0;
  refreshCalls = 0;
  signOutCalls = 0;
  private listener: ((event: string, session: Session | null) => void) | null = null;

  constructor(current: Session | null = null) {
    this.current = current;
  }

  auth = {
    getSession: async () => {
      this.getSessionCalls += 1;
      return { data: { session: this.current }, error: null };
    },
    refreshSession: async () => {
      this.refreshCalls += 1;
      return { data: { session: this.current }, error: null };
    },
    signInWithPassword: async (credentials: { email: string; password: string }) => {
      void credentials;
      if (this.signInError) {
        return { data: { session: null, user: null }, error: { message: "private" } };
      }
      this.current = fakeSession();
      this.listener?.("SIGNED_IN", this.current);
      return { data: { session: this.current, user: fakeUser }, error: null };
    },
    signOut: async () => {
      this.signOutCalls += 1;
      if (this.signOutError) return { error: { message: "private" } };
      this.current = null;
      this.listener?.("SIGNED_OUT", null);
      return { error: null };
    },
    onAuthStateChange: (callback: (event: string, value: Session | null) => void) => {
      this.listener = callback;
      return { data: { subscription: { unsubscribe: () => undefined } } };
    },
  };
}
