import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CourseIdentity, localizedCourseName } from "./CourseIdentity";

describe("name-first canonical course identity", () => {
  it("prefers the requested locale, retains a secondary stable code", () => {
    render(<CourseIdentity courseCode="1501221" nameAr="تراكيب البيانات" nameEn="Data Structures" />);
    expect(screen.getByText("تراكيب البيانات")).toBeTruthy();
    expect(screen.getByText("1501221")).toBeTruthy();
    expect(localizedCourseName("تراكيب البيانات", "Data Structures", "1501221", "en"))
      .toBe("Data Structures");
  });

  it("uses canonical alternate-language name then code without inventing translations", () => {
    expect(localizedCourseName(null, "Data Structures", "1501221", "ar")).toBe("Data Structures");
    expect(localizedCourseName(null, null, "1501221", "ar")).toBe("1501221");
  });
});
