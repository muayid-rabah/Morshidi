import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DecisionHistoryPage from "./page";
import type { StudentDecisionHistoryDetail, StudentDecisionHistoryItem } from "@/lib/api/student-types";

const api = vi.hoisted(() => ({ request: vi.fn() }));
const request = api.request;
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => api }));

const first: StudentDecisionHistoryItem = {
  ledger_entry_id: "11111111-1111-1111-1111-111111111111",
  decision_type: "MOCK_REGISTRATION_SUBMIT", decision_status: "VALIDATED",
  created_at: "2026-09-28T12:00:00Z", source_engine: "mock_registration",
  source_engine_version: "6.5", policy_version: "P8.1",
  replay_status: "REPLAYABLE_EXACT", supersedes_entry_id: null,
  is_superseded: true, limitations: ["TEST_ONLY"], integrity_status: "VERIFIED",
};
const second: StudentDecisionHistoryItem = {
  ...first, ledger_entry_id: "22222222-2222-2222-2222-222222222222",
  decision_type: "FUTURE_SAFE_TYPE", decision_status: "ABSTAINED",
  replay_status: "NOT_REPLAYABLE", is_superseded: false,
};
const detail: StudentDecisionHistoryDetail = {
  ...first, source_versions: ["catalog:v1", "policy:v1"],
  provenance_class: "AUTHORITATIVE_TRANSACTION", supersedes_entry_id: second.ledger_entry_id,
  evidence: [
    { source: "catalog", identifier: "plan-test", version: "v1", locator: "section 2", uri: "https://example.test/source" },
    { source: "policy", identifier: "test-only", version: "v2", locator: "article 4", uri: "javascript:alert(1)" },
  ],
};
function response(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("student Decision History", () => {
  beforeEach(() => request.mockReset());

  it("shows an honest empty state without a demo trace or placeholder", async () => {
    request.mockResolvedValue(response([]));
    render(<DecisionHistoryPage />);
    expect(screen.getByText("جارٍ تحميل سجل القرارات...")).toBeDefined();
    expect(await screen.findByText("لا توجد قرارات موثقة متاحة للعرض في سجلك حالياً.")).toBeDefined();
    expect(screen.queryByText(/قيد التجهيز/)).toBeNull();
    expect(request.mock.calls[0][0]).toBe("/api/v1/me/decision-history?limit=20");
  });

  it("renders Arabic timeline labels, statuses, integrity, replay, and safe future fallback", async () => {
    request.mockResolvedValue(response([first, second]));
    render(<DecisionHistoryPage />);
    expect(await screen.findByText("إرسال تسجيل تجريبي")).toBeDefined();
    expect(screen.getByText("سجل قرار أكاديمي")).toBeDefined();
    expect(screen.getByText("تم التحقق")).toBeDefined();
    expect(screen.getAllByText(/سلامة السجل: تم التحقق/)).toHaveLength(2);
    expect(screen.getByText("قابل للتحقق بالإصدارات التاريخية")).toBeDefined();
    expect(screen.getByText("غير قابل لإعادة التشغيل")).toBeDefined();
    expect(screen.getByText("هذا السجل لم يعد الأحدث.")).toBeDefined();
    expect(screen.getByRole("heading", { name: "سجل القرارات الأكاديمية" })).toBeDefined();
    expect(screen.getByRole("region", { name: "الخط الزمني للقرارات" }).className).toContain("sm:pr-6");
  });

  it("requests the next bounded page using the last stable tuple", async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) => ({
      ...first, ledger_entry_id: String(index + 1).padStart(8, "0"),
    }));
    request.mockResolvedValueOnce(response(firstPage));
    request.mockResolvedValueOnce(response([second]));
    const user = userEvent.setup();
    render(<DecisionHistoryPage />);
    await screen.findByRole("button", { name: "عرض المزيد" });
    await user.click(screen.getByRole("button", { name: "عرض المزيد" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    const url = String(request.mock.calls[1][0]);
    expect(url).toContain("limit=20");
    expect(url).toContain("before_created_at=");
    expect(url).toContain("before_entry_id=00000020");
    expect(screen.queryByRole("button", { name: "عرض المزيد" })).toBeNull();
  });

  it("opens a verified detail with ordered evidence, safe URL, versions, limitations, and supersession", async () => {
    request.mockImplementation(async (path: string | undefined) => response(String(path).includes(first.ledger_entry_id) ? detail : [first]));
    const user = userEvent.setup();
    render(<DecisionHistoryPage />);
    await screen.findByText("إرسال تسجيل تجريبي");
    await user.click(screen.getByRole("button", { name: "عرض التفاصيل" }));
    expect(await screen.findByRole("dialog")).toBeDefined();
    expect(screen.getByText("plan-test", { exact: false })).toBeDefined();
    expect(screen.getByText("test-only", { exact: false })).toBeDefined();
    expect(screen.getByText("policy:v1")).toBeDefined();
    expect(screen.getByText("TEST_ONLY")).toBeDefined();
    expect(screen.getByText("هذا السجل يصحح أو يستبدل سجلاً سابقاً.")).toBeDefined();
    const links = screen.getAllByRole("link", { name: "فتح المصدر ↗" });
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("https://example.test/source");
    expect(links[0].getAttribute("rel")).toBe("noopener noreferrer");
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(screen.queryByText(/integrity_hash|actor_id|previous_entry_hash/i)).toBeNull();
    await user.click(screen.getByRole("button", { name: "إغلاق التفاصيل" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("retries a list failure without exposing internals", async () => {
    request.mockRejectedValueOnce(new Error("private PostgREST payload"));
    request.mockResolvedValueOnce(response([]));
    const user = userEvent.setup();
    render(<DecisionHistoryPage />);
    expect((await screen.findByRole("alert")).textContent).toContain("تعذّر تحميل سجل القرارات");
    expect(screen.queryByText("private PostgREST payload")).toBeNull();
    await user.click(screen.getByRole("button", { name: "إعادة المحاولة" }));
    expect(await screen.findByText("لا توجد قرارات موثقة متاحة للعرض في سجلك حالياً.")).toBeDefined();
  });

  it("clears stale detail on failure and retries the selected record", async () => {
    request.mockImplementation(async (path: string | undefined) => {
      if (!String(path).includes("/decision-history/")) return response([first, second]);
      if (String(path).includes(first.ledger_entry_id)) return response(detail);
      throw new Error("private trace internals");
    });
    const user = userEvent.setup();
    render(<DecisionHistoryPage />);
    await screen.findByText("إرسال تسجيل تجريبي");
    await user.click(screen.getAllByRole("button", { name: "عرض التفاصيل" })[0]);
    await screen.findByText("plan-test", { exact: false });
    await user.click(screen.getByRole("button", { name: "إغلاق التفاصيل" }));
    await user.click(screen.getAllByRole("button", { name: "عرض التفاصيل" })[1]);
    expect((await screen.findByRole("alert")).textContent).toContain("تعذّر تحميل تفاصيل هذا السجل");
    expect(screen.queryByText("plan-test", { exact: false })).toBeNull();
    expect(screen.queryByText("private trace internals")).toBeNull();
    await user.click(screen.getByRole("button", { name: "إعادة المحاولة" }));
    await waitFor(() => expect(request.mock.calls.filter(([path]) => String(path).includes(second.ledger_entry_id))).toHaveLength(2));
  });

  it("never renders an unverified detail even if a malformed response reaches the client", async () => {
    request.mockImplementation(async (path: string | undefined) => response(String(path).includes(first.ledger_entry_id) ? {
      ...detail, integrity_status: "TAMPER_DETECTED",
    } : [first]));
    const user = userEvent.setup();
    render(<DecisionHistoryPage />);
    await screen.findByText("إرسال تسجيل تجريبي");
    await user.click(screen.getByRole("button", { name: "عرض التفاصيل" }));
    expect((await screen.findByRole("alert")).textContent).toContain("تعذّر تحميل تفاصيل هذا السجل");
    expect(screen.queryByText("plan-test", { exact: false })).toBeNull();
  });
});
