import { describe, expect, it } from "vitest";
import manifest from "./manifest";

describe("P9 local PWA manifest contract", () => {
  it("provides an install-oriented public shell without private offline caching", () => {
    const data = manifest();
    expect(data.name).toBeTruthy();
    expect(data.short_name).toBeTruthy();
    expect(data.start_url).toBe("/");
    expect(data.scope).toBe("/");
    expect(data.display).toBe("standalone");
    expect(data.lang).toBe("ar");
    expect(data.dir).toBe("rtl");
    expect(data.theme_color).toBe("#805400");
    expect(data.icons?.some((icon) => icon.src === "/favicon.ico")).toBe(true);
  });
});
