import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { AuthProvider } from "@/auth/auth-provider";
import { LoginForm } from "@/auth/login-form";
import { FakeAuthClient } from "@/test/fake-auth-client";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
  useSearchParams: () => new URLSearchParams("returnTo=/student"),
}));

test("Arabic RTL login is keyboard accessible and uses email/password", async () => {
  const client = new FakeAuthClient();
  render(
    <div dir="rtl">
      <AuthProvider client={client}><LoginForm /></AuthProvider>
    </div>,
  );
  const email = screen.getByLabelText("البريد الإلكتروني");
  const password = screen.getByLabelText("كلمة المرور");
  expect(email.getAttribute("dir")).toBe("ltr");
  await userEvent.type(email, "student@example.com");
  await userEvent.type(password, "password{Enter}");
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/student"));
  expect(document.querySelector("[dir='rtl']")).toBeTruthy();
  expect(document.body.textContent).not.toContain("current-access-token");
});

test("sign-in failure shows a safe Arabic error", async () => {
  const client = new FakeAuthClient();
  client.signInError = true;
  render(<AuthProvider client={client}><LoginForm /></AuthProvider>);
  await userEvent.type(screen.getByLabelText("البريد الإلكتروني"), "student@example.com");
  await userEvent.type(screen.getByLabelText("كلمة المرور"), "wrong{Enter}");
  expect((await screen.findByRole("alert")).textContent).toContain(
    "تعذّر تسجيل الدخول",
  );
  expect(document.body.textContent).not.toContain("private");
});
