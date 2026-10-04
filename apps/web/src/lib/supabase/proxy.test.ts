import { isProtectedStudentPath } from "@/lib/supabase/proxy";
import { config } from "@/proxy";

test.each(["/student", "/student/profile", "/student/results/current"])(
  "protects student path %s",
  (path) => expect(isProtectedStudentPath(path)).toBe(true),
);

test.each(["/", "/login", "/advisor", "/students"])(
  "does not broaden the protected matcher to %s",
  (path) => expect(isProtectedStudentPath(path)).toBe(false),
);

test("protects the focused institutional change-impact route", () => {
  expect(isProtectedStudentPath("/institutional/change-impact")).toBe(true);
  expect(isProtectedStudentPath("/institutional/other")).toBe(false);
  expect(config.matcher).toContain("/institutional/change-impact");
});

test("protects the focused institutional AI query route", () => {
  expect(isProtectedStudentPath("/institutional/ai-query")).toBe(true);
  expect(config.matcher).toContain("/institutional/ai-query");
});

test("protects the analyst-only cohort explorer route", () => {
  expect(isProtectedStudentPath("/institutional/cohorts")).toBe(true);
  expect(config.matcher).toContain("/institutional/cohorts");
});
