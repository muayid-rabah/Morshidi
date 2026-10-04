# Frontend authentication and session boundary

## Scope and original blocker

Phase 10.7 was paused because the web application did not have an authenticated session boundary through which the planned advisor experience could safely call the existing FastAPI API. Phase 10.7A supplies that boundary only. It does not add advisor routes, chat components, prompt suggestions, provider calls, or academic-state persistence.

The implementation targets Next.js 16.3.5 and React 19.2.8. It uses the official Supabase SSR architecture: `@supabase/ssr` 0.12.7 and `@supabase/supabase-js` 2.116.0, with a browser client, a server client backed by Next.js cookies, and a Next.js 16 `proxy.ts` refresh and route-UX boundary. The deprecated auth-helpers packages are not used.

## Configuration

The browser-visible configuration is limited to:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`

Never expose `SUPABASE_SECRET_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `ADVISOR_LLM_API_KEY`, `OPENAI_API_KEY`, or any equivalent provider secret as a `NEXT_PUBLIC_*` variable. The example environment file contains placeholders only.

## Client and proxy responsibilities

`src/lib/supabase/client.ts` creates the singleton browser client with `createBrowserClient`. `src/lib/supabase/server.ts` creates request-scoped server clients with `createServerClient` and the asynchronous Next.js cookies API. Cookie writes that are unavailable from Server Components are safely deferred to the proxy.

`src/proxy.ts` delegates to the session helper for `/login` and `/student/:path*`. The helper calls `supabase.auth.getClaims()` so expired sessions can be refreshed and all resulting cookies are forwarded on the returned response. It redirects an unauthenticated `/student` request to `/login` with a constrained `returnTo` value, and redirects an already authenticated login request to `/student`. These redirects are a UX guard, not an authorization decision.

## Session lifecycle

`AuthProvider` is the canonical client-side session abstraction. It starts in `loading`, resolves the current Supabase session, subscribes to official auth state changes, and exposes the authenticated user plus sign-in, sign-out, current-token, refresh, and invalidation operations. Missing public configuration has a safe `configuration_error` state.

Sign-in uses Supabase email/password authentication only. The Arabic-first RTL login form has native labels, required fields, password autocomplete, a submitting state, keyboard submission, and a safe generic error. It neither renders tokens nor returns raw provider errors. Sign-out calls canonical `supabase.auth.signOut()`, clears the authenticated UI state, and returns the user to login. The reusable student layout keeps protected content unmounted during loading and after logout.

Supabase owns session persistence and its SSR cookie/browser behavior. The application does not create a token in `localStorage`, `sessionStorage`, IndexedDB, or any other application-owned store. It also does not persist academic state or advisor conversations.

## FastAPI access and security authority

`AuthenticatedApiClient` is the sole authenticated FastAPI boundary. Before every request it asks `AuthProvider` for the current Supabase session token, then adds `Authorization: Bearer <access_token>` to `NEXT_PUBLIC_API_BASE_URL`. Callers provide only `/api/v1/me/...` paths and never construct authentication headers or append an owner/user identifier.

On HTTP 401 the client asks Supabase to refresh the session. It retries at most once, and only when Supabase supplies a token that is genuinely different from the rejected token. A missing refresh or a persistent 401 invalidates the local session and reports `UNAUTHENTICATED`. HTTP 403 remains the distinct `FORBIDDEN` result. Validation, server, service-unavailable, and network failures also have stable typed codes; raw stacks and provider errors are not exposed.

The browser does not decode or authorize a JWT. FastAPI remains the security authority: it receives the Supabase access token, verifies the user through the existing Supabase `/auth/v1/user` flow, and enforces ownership and academic authorization server-side.

## Test and dependency baseline

The focused test stack is Vitest 4.1.11, jsdom 29.1.1, Testing Library React 16.3.3, and Testing Library user-event 14.6.7. It covers loading and session resolution, sign-in success/failure, sign-out cleanup, protected-content suppression, RTL and keyboard form behavior, current bearer-token forwarding, no-token suppression, one-time 401 refresh, persistent 401 invalidation, 403 and other error mappings, request-body preservation, public configuration, official API usage, and forbidden storage/secrets/advisor code. Proxy path coverage verifies that only the student area is classified as protected.

## Phase 10.7 resume point

Resume Phase 10.7 by building the Arabic-first advisor experience inside the existing protected `/student` shell. Use `useAuthenticatedApi()` for every FastAPI request and preserve the established `/api/v1/me/...` contract. Do not add another auth system, manually construct bearer headers, pass a user ID, decode JWT claims for authorization, persist advisor or academic data in the browser, or call an LLM provider from the frontend.
