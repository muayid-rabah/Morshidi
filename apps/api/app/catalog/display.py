"""Canonical display metadata; never an academic decision or identity substitute."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CourseDisplayIdentity:
    course_id: str
    course_code: str
    name_ar: str | None
    name_en: str | None
