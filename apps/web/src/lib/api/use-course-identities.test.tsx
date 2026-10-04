import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { CourseIdentity } from "@/components/academic/CourseIdentity";
import { useCourseIdentities } from "./use-course-identities";

const client = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => client }));
const rows = [
  { course_id: "c-1", course_code: "CS101", name_ar: "مقدمة", name_en: "Introduction" },
  { course_id: "c-2", course_code: "CS201", name_ar: null, name_en: "Advanced course" },
];
function Harness({ enabled = true, university, locale = "ar" }: {
  enabled?: boolean; university?: string; locale?: "ar" | "en";
}) {
  const identities = useCourseIdentities(enabled, university);
  return <>{["CS101", "CS201", "UNKNOWN"].map(code =>
    <CourseIdentity key={code} courseCode={code} identities={identities} locale={locale} />)}</>;
}
beforeEach(() => { client.request.mockReset(); });

test("one batch provides Arabic-first and English-first names, code secondary, and safe fallback", async () => {
  client.request.mockImplementation(async () => new Response(JSON.stringify(rows)));
  const view = render(<Harness />);
  expect((await screen.findByText("مقدمة")).parentElement!.textContent).toBe("مقدمةCS101");
  expect(screen.getByText("Advanced course")).toBeTruthy();
  expect(screen.getByText("UNKNOWN")).toBeTruthy();
  view.rerender(<Harness locale="en" />);
  expect(screen.getByText("Introduction").parentElement!.textContent).toBe("IntroductionCS101");
  expect(client.request).toHaveBeenCalledTimes(1);
});

test("no academic catalog request until a human-facing course reference is needed", async () => {
  client.request.mockImplementation(async () => new Response(JSON.stringify(rows)));
  const view = render(<Harness enabled={false} />);
  expect(client.request).not.toHaveBeenCalled();
  view.rerender(<Harness />);
  await screen.findByText("مقدمة");
  expect(client.request).toHaveBeenCalledTimes(1);
});

test("tenant change immediately clears the prior display map and ignores a late response", async () => {
  let finishOld: (value: Response) => void = () => {};
  client.request.mockImplementation((path: string) => path.endsWith("A")
    ? new Promise<Response>(resolve => { finishOld = resolve; })
    : Promise.resolve(new Response(JSON.stringify([{ ...rows[0], name_ar: "جامعة ب" }]))));
  const view = render(<Harness university="A" />);
  view.rerender(<Harness university="B" />);
  await screen.findByText("جامعة ب");
  await act(async () => { finishOld(new Response(JSON.stringify(rows))); });
  expect(screen.queryByText("مقدمة")).toBeNull();
  expect(screen.getByText("جامعة ب")).toBeTruthy();
  view.rerender(<Harness enabled={false} university="B" />);
  await waitFor(() => expect(screen.queryByText("جامعة ب")).toBeNull());
});
