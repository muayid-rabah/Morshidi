# Morshidi Academic Data Model

## Status

Project: Morshidi  
University: Zarqa University  
Initial Major: Artificial Intelligence  
Study Plan: Plan 12  
Required Graduation Hours: 132  

This document defines the canonical academic structure used by Morshidi.

No database implementation should begin until this model is reviewed,
validated against the official study plan, and approved.

---

# 1. University

Represents a university supported by Morshidi.

Fields:

- id
- name_ar
- name_en
- country
- website
- active

Example:

University:

جامعة الزرقاء  
Zarqa University

Relationship:

University
└── Faculties

---

# 2. Faculty

Represents a faculty inside a university.

Fields:

- id
- university_id
- name_ar
- name_en
- code
- active

Relationship:

University
└── Faculty

Example:

جامعة الزرقاء
└── كلية تكنولوجيا المعلومات

Important:

A university may contain multiple faculties.

---

# 3. Major

Represents an academic major inside a faculty.

Fields:

- id
- faculty_id
- name_ar
- name_en
- code
- active

Relationship:

University
└── Faculty
    └── Major

Initial supported major:

الذكاء الاصطناعي

Future supported majors:

- علم الحاسوب
- هندسة البرمجيات
- الأمن السيبراني

Important:

A faculty may contain multiple majors.

The Major entity represents the academic program itself.

Study-plan-specific information must NOT be stored directly inside Major.

---

# 4. Study Plan

Represents a specific academic study plan for a major.

Fields:

- id
- major_id
- plan_number
- total_credit_hours
- effective_year
- status
- source_id
- notes

Possible status values:

- active
- archived
- draft
- unknown

Example:

Major:

الذكاء الاصطناعي

Study Plan:

Plan 12

Total Credit Hours:

132

Important:

A major may have multiple study plans.

Example:

Artificial Intelligence
├── Plan 10
├── Plan 11
└── Plan 12

Every student must always be linked to a specific Study Plan.

Academic rules belonging to another Study Plan must never
automatically affect the student.

---

# 5. Requirement Group

Represents an academic requirement category inside a Study Plan.

Fields:

- id
- study_plan_id
- name_ar
- name_en
- requirement_type
- required_credit_hours
- minimum_courses
- maximum_courses
- display_order
- active
- notes

Possible requirement_type values:

- required
- elective
- supporting
- other

Initial Artificial Intelligence Plan 12 requirement groups:

1. متطلبات الجامعة الإجبارية — 18 ساعة
2. متطلبات الجامعة الاختيارية — 9 ساعات
3. متطلبات الكلية الإجبارية — 21 ساعة
4. المتطلبات المساندة — 12 ساعة
5. متطلبات التخصص الإجبارية — 63 ساعة
6. متطلبات التخصص الاختيارية — 9 ساعات

Total:

132 credit hours

Important:

For elective groups, required_credit_hours represents how many
credit hours the student must successfully complete.

It does NOT represent the total credit hours of all courses listed
inside the elective pool.

Example:

متطلبات التخصص الاختيارية

Required:

9 credit hours

Available courses may total:

39 credit hours

The student only needs to satisfy the required 9 credit hours.

---

# 6. Course

Represents the identity of a university course.

Fields:

- id
- university_id
- course_code
- name_ar
- name_en
- catalog_status
- active
- notes

Possible catalog_status values:

- known
- referenced_only
- legacy
- unknown

Example:

course_code:

1505311

name_ar:

تعلم الآلة

catalog_status:

known

Important:

A Course is independent from a Study Plan.

The same Course may appear in multiple majors and multiple study plans.

Therefore the Course must NOT be duplicated every time it appears
inside another Study Plan.

Example:

1501110 — برمجة الحاسوب (1)

may appear in:

- Artificial Intelligence Plan 12
- Computer Science Study Plan
- Software Engineering Study Plan
- Cyber Security Study Plan

but it remains one Course record.

---

## Referenced-Only Courses

A course may appear as a prerequisite even when it is NOT listed
as a selectable course inside the student's Study Plan.

In this situation Morshidi must still preserve the course reference.

Example:

Artificial Intelligence Plan 12 references:

0300103

as a prerequisite.

However, 0300103 is not listed as a selectable course inside the
current Artificial Intelligence Plan 12 data.

Morshidi must create or maintain:

Course:

0300103

catalog_status:

referenced_only

If the official course name is not yet verified, name_ar and name_en
may remain null.

Morshidi must NOT:

- delete the prerequisite
- replace the code automatically
- guess the course name
- assume equivalency with another course
- silently modify the university data

The reference must remain exactly as published until verified.

---

# 7. Study Plan Course

Connects a Course to a specific Study Plan.

Fields:

- id
- study_plan_id
- course_id
- requirement_group_id
- requirement_type
- credit_hours
- learning_type
- delivery_mode
- raw_prerequisite_text
- verification_status
- source_id
- display_order
- active
- notes

Relationship:

Study Plan
└── Requirement Group
    └── Study Plan Course
        └── Course

Example:

Course:

1501110 — برمجة الحاسوب (1)

may appear inside:

- Artificial Intelligence Plan 12
- Computer Science Study Plan
- Software Engineering Study Plan
- Cyber Security Study Plan

Study Plan Course defines how that Course behaves inside each
specific Study Plan.

---

## Credit Hours

credit_hours belongs to Study Plan Course.

This preserves the exact credit-hour value published for that
course inside that specific Study Plan.

Morshidi must not assume that all historical or future appearances
of a course always have identical plan-specific properties.

---

## Learning Type

learning_type preserves the academic learning method published
inside the Study Plan.

Examples from Plan 12 include:

- نظري
- عملي
- التعلم القائم على المشاريع

---

## Delivery Mode

delivery_mode stores the published delivery mode.

Examples:

- وجاهي
- مدمج
- الكتروني

---

## Raw Prerequisite Text

raw_prerequisite_text stores the prerequisite representation
exactly as published by the university.

Example:

0300103,1505311

The original value must be preserved even after Morshidi converts
the prerequisite into structured rules.

Architecture:

Official University Source
↓
raw_prerequisite_text
↓
Structured Prerequisite Rules
↓
Rules Engine

The raw value exists for:

- traceability
- auditing
- debugging
- future corrections
- verification against the official source

Morshidi must never overwrite the raw official value when
interpreting prerequisite logic.

---

## Verification Status

verification_status indicates whether the Plan Course data
has been reviewed.

Possible values:

- verified
- needs_review
- unresolved
- source_conflict

Example:

A course may be verified as appearing in the official Plan,
while one of its prerequisite references remains unresolved.

---

# 8. Prerequisite Group

Represents structured prerequisite logic for a Study Plan Course.

Fields:

- id
- study_plan_course_id
- group_number
- notes

Prerequisite Groups are combined using AND logic.

Prerequisite Options inside the same group are combined using OR logic.

---

## Example 1

Course X requires:

A AND B

Representation:

Group 1:
- A

Group 2:
- B

Meaning:

A AND B

---

## Example 2

Course X requires:

A AND (B OR C)

Representation:

Group 1:
- A

Group 2:
- B
- C

Meaning:

A AND (B OR C)

---

## Why This Structure Exists

Prerequisites must NOT exist only as plain text.

Plain text is preserved in:

raw_prerequisite_text

Structured prerequisite data is used by:

Rules Engine

This allows Morshidi to compute academic eligibility
without relying on text parsing during every request.

---

# 9. Prerequisite Option

Represents one allowed prerequisite Course inside a
Prerequisite Group.

Fields:

- id
- prerequisite_group_id
- prerequisite_course_id
- minimum_grade
- verification_status
- notes

Possible verification_status values:

- verified
- referenced_only
- unresolved
- source_conflict

---

## Example

Course:

1505320 — تعلم الآلة المتقدم

Official prerequisite representation:

0300103,1505311

Structured representation:

Group 1:
- 0300103

Group 2:
- 1505311

Meaning:

0300103 AND 1505311

Course 0300103 may exist as:

catalog_status = referenced_only

Course 1505311 may exist as:

catalog_status = known

Both Courses can participate in prerequisite relationships.

This allows Morshidi to preserve official academic rules
without inventing missing information.

---

# 10. Course Equivalency

Represents officially confirmed relationships between courses.

Fields:

- id
- university_id
- course_id
- equivalent_course_id
- equivalency_type
- effective_from
- effective_to
- source_id
- verification_status
- active
- notes

Possible equivalency_type values:

- equivalent
- replacement
- legacy_code
- unknown

Possible verification_status values:

- verified
- pending
- unresolved
- rejected

Important:

Morshidi must NEVER assume course equivalency automatically.

An equivalency must have an official source before the Rules Engine
is allowed to use it.

---

## Current Unresolved Plan 12 References

Current Plan 12 data contains references involving:

0300103

while the supporting requirements currently list:

0300104

and:

0301241

while the supporting requirements currently list:

0301245

Possible relationships may exist between:

0300103 ↔ 0300104

and:

0301241 ↔ 0301245

However:

These relationships are NOT considered valid equivalencies
until officially confirmed.

Until confirmation:

The Rules Engine must NOT automatically treat them as interchangeable.

---

# 11. Academic Source

Stores the origin of academic information used by Morshidi.

Fields:

- id
- university_id
- source_type
- source_url
- title
- retrieved_at
- plan_number
- source_status
- notes

Possible source_type values:

- official_webpage
- official_pdf
- official_study_plan
- university_regulation
- university_course_catalog
- manual_verification

Possible source_status values:

- active
- archived
- unavailable
- unknown

Important:

Every important academic rule should be traceable to an
official or documented source.

Examples:

Study Plan
→ Academic Source

Study Plan Course
→ Academic Source

Course Equivalency
→ Academic Source

This allows Morshidi to answer:

"Where did this academic rule come from?"

---

# 12. Future Student Model

The Student model is NOT implemented during the current Phase.

It is documented here only to ensure that the Academic Data Model
will support future development.

Future entities may include:

Student
Student Study Plan
Student Course Record
Student Semester
Student Academic Status

A Student will eventually reference:

- University
- Faculty
- Major
- Study Plan

The student's academic history will then be evaluated against
the structures defined in this document.

Student implementation belongs to a later development Phase.

---

# Core Relationships

University
│
├── Academic Sources
│
├── Courses
│
└── Faculties
    │
    └── Major
        │
        └── Study Plan
            │
            ├── Requirement Groups
            │
            └── Study Plan Courses
                │
                ├── Course
                │
                └── Prerequisite Groups
                    │
                    └── Prerequisite Options
                        │
                        └── Prerequisite Course

Course
│
└── Course Equivalencies

Academic Source
│
├── Study Plan
├── Study Plan Course
└── Course Equivalency

---

# Data Flow

Official University Source
↓
Academic Source
↓
Study Plan Data
↓
Requirement Groups
↓
Study Plan Courses
↓
Raw Prerequisites
↓
Structured Prerequisite Rules
↓
Rules Engine
↓
Academic Decision
↓
AI Explanation

---

# Core Design Principles

## 1. No Hardcoding

Academic rules must come from structured academic data.

The application code must NOT contain rules such as:

if course == "1505311":
    require("1505101")

Instead:

The Rules Engine reads the prerequisite relationship
from structured academic data.

This allows academic rules to change without changing application code.

---

## 2. Source First

Official university data is the source of truth.

Morshidi must never silently modify official data.

If the official source contains something unusual or unresolved,
Morshidi preserves it and marks its verification status.

---

## 3. Preserve Raw Data

Morshidi must preserve the original academic value before
converting it into structured logic.

Example:

Official value:

0300103,1505311

must remain stored even after creating structured prerequisite records.

---

## 4. Never Guess Academic Rules

Morshidi must NOT automatically guess:

- course equivalencies
- replacement courses
- prerequisite replacements
- missing course names
- changed course codes
- academic exceptions

Unknown information must remain explicitly unknown.

---

## 5. Deterministic Academic Rules

Academic eligibility must be calculated by deterministic
Rules Engine logic.

LLMs must NOT decide whether a student is academically eligible
for a Course.

---

## 6. AI Explains — Rules Decide

Correct architecture:

Academic Data
↓
Rules Engine
↓
Academic Decision
↓
AI Explanation

Incorrect architecture:

Student Question
↓
LLM
↓
Academic Decision

The LLM may explain a decision.

The LLM must NOT create the academic decision itself.

---

## 7. Plan Versioning

Every Student must belong to a specific Study Plan.

Rules from another Study Plan must never automatically
affect that Student.

Example:

A student following Plan 12 must be evaluated using Plan 12 rules.

Plan 11 or Plan 13 rules must not be mixed into the calculation
unless an officially documented relationship requires it.

---

## 8. Shared Courses

Courses must exist independently from Study Plans.

A Course may appear in:

- multiple majors
- multiple faculties
- multiple Study Plans

without duplicating its core identity.

Plan-specific information belongs to Study Plan Course.

---

## 9. Referenced-Only Courses Are Valid Data

A Course does not need to appear inside the student's current
Study Plan to exist in Morshidi.

If it appears as an official prerequisite reference,
it is valid academic data.

Example:

0300103

may exist with:

catalog_status = referenced_only

until more information is officially verified.

---

## 10. Traceability

Every important academic decision should eventually be traceable.

Example:

Student cannot take Course X
↓
Prerequisite Y is incomplete
↓
Prerequisite relationship came from Study Plan Course X
↓
Study Plan Course X came from Official Source Z

This is essential for trust and debugging.

---

## 11. Reusability

The architecture must support:

- multiple universities
- multiple faculties
- multiple majors
- multiple Study Plans
- shared Courses
- changed Course codes
- legacy Courses
- referenced-only Courses
- Course equivalencies
- replacement Courses
- elective groups
- zero-credit Courses
- future curriculum changes

without redesigning the entire system.

---

## 12. Arabic Is Canonical for Initial Data

The initial official Zarqa University source is Arabic.

For the first Morshidi version:

name_ar is the canonical verified Course name when sourced
from the official Arabic Study Plan.

name_en may remain null until officially verified or
intentionally translated later.

Morshidi must not present an unofficial English translation
as official university data.

---

# Current Plan 12 Validation Rules

For Artificial Intelligence Plan 12:

Required Graduation Hours:

132

Requirement Groups:

University Required:
18 hours

University Elective:
9 hours

Faculty Required:
21 hours

Supporting Requirements:
12 hours

Major Required:
63 hours

Major Elective:
9 hours

Total:

132 hours

---

## Zero-Credit Courses

Plan 12 includes Courses with zero credit hours.

These Courses must remain in the Study Plan.

A zero-credit Course must NOT automatically be ignored simply because
it contributes zero hours toward the graduation total.

The academic completion requirement may still be important.

---

## Elective Courses

An elective pool may contain more total Course hours than
the Student is required to complete.

Example:

Major Electives may contain many available Courses.

Required:

9 credit hours

Morshidi must calculate completion based on:

required_credit_hours

not:

sum of every Course in the elective pool.

---

## Duplicate Source Rows

If the same Course appears twice because an official table was split
between screenshots or pages, it must NOT automatically become
two Study Plan Course records.

Example:

1505320 — تعلم الآلة المتقدم

appeared at the boundary between two screenshots during
Phase 1 extraction.

It represents one Study Plan Course only.

---

# Phase 1 Result

Academic Source of Truth:

COMPLETED

Current dataset:

Zarqa University  
Artificial Intelligence  
Study Plan 12

Extracted academic records:

68

Graduation Hours:

132

Known unresolved prerequisite references:

- 0300103
- 0301241

Additional prerequisite references that do not appear as selectable
Plan 12 Courses are preserved as referenced-only Courses.

---

# Phase 2 Validation Checklist

[x] University entity defined

[x] Faculty entity defined

[x] Major entity defined

[x] Study Plan entity defined

[x] Requirement Group entity defined

[x] Course entity defined

[x] Study Plan Course relationship defined

[x] Course credit hours moved to Study Plan Course

[x] Raw prerequisite preservation defined

[x] Referenced-only Course support defined

[x] Prerequisite Group model defined

[x] Prerequisite Option model defined

[x] Course Equivalency model defined

[x] Academic Source model defined

[x] Plan versioning defined

[x] Source traceability defined

[x] Zero-credit Course behavior documented

[x] Elective requirement behavior documented

[x] Arabic canonical-data rule defined

[ ] Test representative Zarqa University Plan 12 Courses

[ ] Test referenced-only prerequisite Courses

[ ] Test required requirement groups

[ ] Test elective requirement groups

[ ] Test zero-credit Courses

[ ] Test multi-prerequisite Courses

[ ] Verify that every Phase 1 Excel record can be represented

[ ] Final Academic Data Model review

[ ] Approve Academic Data Model

---

# Phase 2 Status

PHASE 2 STATUS: IN PROGRESS

Current Step:

MODEL VALIDATION

Next Step:

Validate this model against representative real Courses from
Zarqa University Artificial Intelligence Plan 12.

No database implementation should begin until Phase 2 is approved.