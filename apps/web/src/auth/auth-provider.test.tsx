import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import {
  AuthProvider,
  useAuth,
} from "@/auth/auth-provider";
import { ProtectedBoundary } from "@/auth/protected-boundary";
import { FakeAuthClient, fakeSession } from "@/test/fake-auth-client";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
  useSearchParams: () => new URLSearchParams(),
}));

function Harness() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span>{auth.user?.email}</span>
      <button onClick={() => void auth.signIn("student@example.com", "password")}>دخول</button>
      <button onClick={() => void auth.signOut()}>خروج</button>
    </div>
  );
}

test("starts loading and resolves a valid session as authenticated without rendering tokens", async () => {
  let resolveSession!: (value: Awaited<ReturnType<FakeAuthClient["auth"]["getSession"]>>) => void;
  const client = new FakeAuthClient(fakeSession());
  client.auth.getSession = () =>
    new Promise((resolve) => {
      resolveSession = resolve;
    });
  render(<AuthProvider client={client}><Harness /></AuthProvider>);
  expect(screen.getByTestId("status").textContent).toBe("loading");
  expect(document.body.textContent).not.toContain("current-access-token");
  resolveSession({ data: { session: fakeSession() }, error: null });
  await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
  expect(screen.getByText("student@example.com")).toBeTruthy();
  expect(document.body.textContent).not.toContain("private-refresh-token");
});

test("no session resolves as unauthenticated", async () => {
  render(<AuthProvider client={new FakeAuthClient()}><Harness /></AuthProvider>);
  await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
});

test("email/password sign-in succeeds and failure remains safe", async () => {
  const success = new FakeAuthClient();
  const view = render(<AuthProvider client={success}><Harness /></AuthProvider>);
  await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
  await userEvent.click(screen.getByRole("button", { name: "دخول" }));
  await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
  view.unmount();

  const failure = new FakeAuthClient();
  failure.signInError = true;
  render(<AuthProvider client={failure}><Harness /></AuthProvider>);
  await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
  await userEvent.click(screen.getByRole("button", { name: "دخول" }));
  expect(screen.getByTestId("status").textContent).toBe("unauthenticated");
  expect(document.body.textContent).not.toContain("private");
});

test("sign-out clears authenticated and protected transient UI", async () => {
  const client = new FakeAuthClient(fakeSession());
  function ProtectedHarness() {
    const auth = useAuth();
    return (
      <ProtectedBoundary>
        <p>بيانات أكاديمية مؤقتة</p>
        <button onClick={() => void auth.signOut()}>خروج</button>
      </ProtectedBoundary>
    );
  }
  render(<AuthProvider client={client}><ProtectedHarness /></AuthProvider>);
  await screen.findByText("بيانات أكاديمية مؤقتة");
  fireEvent.click(screen.getByRole("button", { name: "خروج" }));
  await waitFor(() => expect(screen.queryByText("بيانات أكاديمية مؤقتة")).toBeNull());
  expect(client.signOutCalls).toBe(1);
  expect(replace).toHaveBeenCalledWith("/login");
});

test("protected content never renders while loading or unauthenticated", async () => {
  const client = new FakeAuthClient();
  render(
    <AuthProvider client={client}>
      <ProtectedBoundary><p>خاص</p></ProtectedBoundary>
    </AuthProvider>,
  );
  expect(screen.queryByText("خاص")).toBeNull();
  expect(screen.getByRole("status")).toBeTruthy();
  await waitFor(() => expect(screen.queryByText("خاص")).toBeNull());
});
