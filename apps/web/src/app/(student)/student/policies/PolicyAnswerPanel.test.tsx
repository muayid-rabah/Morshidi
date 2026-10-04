import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PolicyAnswerPanel } from "./PolicyAnswerPanel";
import type { StudentPolicyAnswerResponse } from "@/lib/api/student-types";

const request = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/use-authenticated-api", () => ({
  useAuthenticatedApi: () => ({ request }),
}));

const citation: StudentPolicyAnswerResponse["citations"][number] = {
  document_id: "synthetic-doc", document_code: "SYNTHETIC-WITHDRAWAL",
  document_title: "لائحة اختبارية للانسحاب", version_id: "synthetic-v1",
  version_tag: "test-1", passage_id: "withdrawal-p1", locator_text: "المادة 4",
  article_number: "4", section_number: "2", page_number: 7, heading: "الانسحاب",
  passage_text: "نص اختباري موثق عن الانسحاب.",
  source_url: "https://example.test/synthetic-source", passage_sha256: "a".repeat(64),
};

const answered: StudentPolicyAnswerResponse = {
  status: "ANSWERED", answer: "يشرح النص الاختباري طريقة الانسحاب.", language: "ar",
  citations: [citation], retrieval_mode: "hybrid", abstention_reason: null, handoff: null,
};

const abstained: StudentPolicyAnswerResponse = {
  status: "ABSTAINED", answer: null, language: "ar", citations: [],
  retrieval_mode: "hybrid", abstention_reason: "NO_VERIFIED_POLICY_EVIDENCE", handoff: null,
};

function jsonResponse(body: StudentPolicyAnswerResponse) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });
}

async function ask(question: string) {
  const user = userEvent.setup();
  render(<PolicyAnswerPanel />);
  await user.type(screen.getByLabelText("سؤال عام عن اللوائح"), question);
  await user.click(screen.getByRole("button", { name: "اسأل عن اللوائح" }));
  return user;
}

describe("grounded policy answer panel", () => {
  beforeEach(() => request.mockReset());

  it("shows a grounded Arabic answer, multiple exact citations, passage text, and safe source links", async () => {
    request.mockResolvedValue(jsonResponse({
      ...answered, citations: [citation, {
        ...citation, passage_id: "attendance-p1", document_title: "لائحة اختبارية للغياب",
        version_tag: "test-2", locator_text: "المادة 8", passage_text: "نص اختباري موثق عن الغياب.",
      }],
    }));
    const user = await ask("ما سياسة الانسحاب؟");
    await screen.findByText("يشرح النص الاختباري طريقة الانسحاب.");
    expect(screen.getAllByText("عرض النص الموثق")).toHaveLength(2);
    expect(screen.getByText(/لائحة اختبارية للانسحاب · إصدار test-1/)).toBeDefined();
    expect(screen.getByText(/المادة 4 · المادة 4 · القسم 2 · الصفحة 7/)).toBeDefined();
    await user.click(screen.getAllByText("عرض النص الموثق")[0]);
    expect(screen.getByText("نص اختباري موثق عن الانسحاب.")).toBeDefined();
    expect(screen.getAllByRole("link", { name: "فتح المصدر ↗" })[0].getAttribute("rel")).toBe("noopener noreferrer");
    const [path, init] = request.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/me/policies/answer");
    expect(JSON.parse(String(init.body))).toEqual({ question: "ما سياسة الانسحاب؟", limit: 6 });
  });

  it("abstains honestly when the production-like corpus is empty", async () => {
    request.mockResolvedValue(jsonResponse(abstained));
    await ask("ما رسوم موقف السيارات؟");
    expect(await screen.findByText("لا توجد أدلة كافية في اللوائح الموثقة للإجابة عن هذا السؤال.")).toBeDefined();
    expect(screen.queryByText(answered.answer as string)).toBeNull();
  });

  it("routes deterministic questions to an existing student page", async () => {
    request.mockResolvedValue(jsonResponse({
      ...abstained, status: "HANDOFF_REQUIRED", abstention_reason: null,
      handoff: { target_engine: "ELIGIBILITY_ENGINE", query_topic: "COURSE_ELIGIBILITY", reason: "Deterministic engine required" },
    }));
    await ask("هل يمكنني تسجيل مادة الذكاء الاصطناعي؟");
    expect(await screen.findByText(/يتطلب هذا السؤال حساباً من محرك مرشدي الأكاديمي/)).toBeDefined();
    expect(screen.getByRole("link", { name: "التحقق من أهلية المساق" }).getAttribute("href")).toBe("/student/eligibility");
    expect(screen.queryByText(answered.answer as string)).toBeNull();
  });

  it("never displays an answer without citations or an unsafe source link", async () => {
    request.mockResolvedValue(jsonResponse({ ...answered, citations: [] }));
    await ask("ما سياسة الانسحاب؟");
    expect(await screen.findByText("لا توجد أدلة كافية في اللوائح الموثقة للإجابة عن هذا السؤال.")).toBeDefined();
    expect(screen.queryByText(answered.answer as string)).toBeNull();
    expect(screen.queryByRole("link", { name: "فتح المصدر ↗" })).toBeNull();
  });

  it("does not render an unsafe citation source as a link", async () => {
    request.mockResolvedValue(jsonResponse({
      ...answered,
      citations: [{ ...citation, source_url: "javascript:alert(1)" }],
    }));
    await ask("ما سياسة الانسحاب؟");
    expect(await screen.findByText(answered.answer as string)).toBeDefined();
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it("shows a safe error and retries without displaying provider internals", async () => {
    request.mockRejectedValueOnce(new Error("private provider payload"));
    request.mockResolvedValueOnce(jsonResponse(abstained));
    const user = await ask("ما سياسة الانسحاب؟");
    expect((await screen.findByRole("alert")).textContent).toContain("خدمة الإجابة عن اللوائح غير متاحة حالياً");
    expect(screen.queryByText("private provider payload")).toBeNull();
    await user.click(screen.getByRole("button", { name: "إعادة المحاولة" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("لا توجد أدلة كافية في اللوائح الموثقة للإجابة عن هذا السؤال.")).toBeDefined();
  });
});
