"use client";

import { useMemo } from "react";

import { useAuth } from "@/auth/auth-provider";
import { AuthenticatedApiClient } from "@/lib/api/authenticated-client";

export function useAuthenticatedApi(): AuthenticatedApiClient {
  const auth = useAuth();
  return useMemo(
    () =>
      new AuthenticatedApiClient({
        getAccessToken: auth.getAccessToken,
        refreshAccessToken: auth.refreshAccessToken,
        invalidateSession: auth.invalidateSession,
      }),
    [auth.getAccessToken, auth.invalidateSession, auth.refreshAccessToken],
  );
}
