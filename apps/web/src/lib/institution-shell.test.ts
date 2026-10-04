import { describe, expect, it } from "vitest";
import { institutionNavVisible, institutionThemeClass, type CurrentInstitution } from "./institution-shell";

const institution: CurrentInstitution = {
  institution_id: "a", display_name: "Institution A", default_locale: "ar",
  supported_locales: ["ar", "en"], theme_key: "sand",
  capabilities: { plan_transition: "MODELED_ONLY", offerings: "UNAVAILABLE" },
  config_version: "v1", config_fingerprint: "fingerprint-a",
};

describe("bounded institution shell", () => {
  it("uses only allowlisted style tokens", () => {
    expect(institutionThemeClass("sand")).toContain("bg-[#FFF4C7]");
    expect(institutionThemeClass("<style>evil</style>")).toBe(institutionThemeClass("default"));
  });

  it("shows modeled navigation but suppresses unavailable capability", () => {
    expect(institutionNavVisible(institution, "plan_transition")).toBe(true);
    expect(institutionNavVisible(institution, "offerings")).toBe(false);
    expect(institutionNavVisible(institution, "unknown")).toBe(false);
    expect(institutionNavVisible(null, "offerings")).toBe(true);
  });
});
