# Morshidi — Phase 2 Academic Data Model Validation

## Status

Project: Morshidi  
University: Zarqa University  
Faculty: Faculty of Information Technology  
Major: Artificial Intelligence  
Study Plan: Plan 12  

Academic Data Model Version: 2.0  
Dataset Records: 68  
Required Graduation Hours: 132  

Phase: 2 — Academic Data Model  
Validation Status: FINAL VALIDATION  

---

# Purpose

This document validates that Morshidi Academic Data Model Version 2.0
can represent the real Zarqa University Artificial Intelligence
Study Plan 12 dataset safely and without hardcoded academic logic.

No database implementation may begin until this validation is approved.

---

# Validation Principles

The model must represent official academic data without:

- inventing missing information
- silently correcting university data
- hardcoding Course-specific rules
- assuming Course equivalencies
- losing original prerequisite values
- duplicating shared Courses unnecessarily
- depending on Arabic display text for application logic
- mixing rules from different Study Plans

Unknown academic information must remain explicitly unknown.

---

# Test 1 — University / Faculty / Major / Study Plan Hierarchy

Expected structure:

University
└── Faculty
    └── Major
        └── Study Plan

Plan 12 representation:

University:

Zarqa University

Faculty:

Faculty of Information Technology

Major:

Artificial Intelligence

Study Plan:

12

Required Graduation Hours:

132

Result:

PASS

The model separates University, Faculty, Major, and Study Plan
instead of storing them as one flat record.

---

# Test 2 — Study Plan Versioning

Requirement:

A Major may have multiple curriculum versions.

Expected representation:

Artificial Intelligence
├── Plan 10
├── Plan 11
└── Plan 12

A future Student must reference one specific Study Plan.

Rules from another Study Plan must not automatically affect that Student.

Result:

PASS

Study Plan is modeled independently from Major.

---

# Test 3 — Machine-Readable Requirement Groups

Plan 12 contains six Requirement Groups.

Expected values:

UNIVERSITY_REQUIRED

scope:
university

requirement_type:
required

required_credit_hours:
18

---

UNIVERSITY_ELECTIVE

scope:
university

requirement_type:
elective

required_credit_hours:
9

---

FACULTY_REQUIRED

scope:
faculty

requirement_type:
required

required_credit_hours:
21

---

SUPPORTING_REQUIRED

scope:
supporting

requirement_type:
required

required_credit_hours:
12

---

MAJOR_REQUIRED

scope:
major

requirement_type:
required

required_credit_hours:
63

---

MAJOR_ELECTIVE

scope:
major

requirement_type:
elective

required_credit_hours:
9

Result:

PASS

The model does not rely on Arabic display names for Rules Engine logic.

---

# Test 4 — Requirement Scope vs Requirement Type

Example:

متطلبات التخصص الاختيارية

Correct representation:

scope:

major

requirement_type:

elective

Incorrect representation:

requirement_type:

major_elective

Result:

PASS

Academic scope and completion behavior are modeled independently.

---

# Test 5 — Graduation-Hour Distribution

Plan 12:

University Required:

18

University Elective:

9

Faculty Required:

21

Supporting Requirements:

12

Major Required:

63

Major Elective:

9

Total:

18 + 9 + 21 + 12 + 63 + 9

=

132 hours

Result:

PASS

Requirement Groups represent the complete graduation-hour structure.

---

# Test 6 — Normal Required Course

Course:

0200104 — التربية الوطنية

Credit Hours:

3

Requirement Group:

UNIVERSITY_REQUIRED

Prerequisite:

None

Expected representation:

Course
└── 0200104
    ├── name_ar: التربية الوطنية
    └── catalog_status: known

Study Plan Course
├── Study Plan: Plan 12
├── Course: 0200104
├── Requirement Group: UNIVERSITY_REQUIRED
├── credit_hours: 3
├── raw_prerequisite_text: null
└── prerequisite_logic_status: not_applicable

Result:

PASS

---

# Test 7 — Zero-Credit Course

Course:

0200115 — تنمية المجتمع والعمل التطوعي

Credit Hours:

0

Expected behavior:

The Course remains inside Plan 12 even though it contributes
zero hours to the graduation-hour total.

Expected representation:

Study Plan Course
├── Course: 0200115
├── credit_hours: 0
└── active: true

Result:

PASS

Zero-credit Courses are valid Plan Courses.

---

# Test 8 — Second Zero-Credit Course

Course:

1509999 — حلقة بحث لطلبة كلية تكنولوجيا المعلومات

Credit Hours:

0

Requirement Group:

FACULTY_REQUIRED

Result:

PASS

Zero-credit support is not limited to one Requirement Group.

---

# Test 9 — Course / Study Plan Course Separation

Example:

1501110 — برمجة الحاسوب (1)

The Course may later appear in:

- Artificial Intelligence
- Computer Science
- Software Engineering
- Cyber Security

Expected architecture:

One Course:

1501110

Multiple Study Plan Course relationships.

Course stores identity.

Study Plan Course stores Plan-specific properties such as:

- credit_hours
- learning_type
- delivery_mode
- Requirement Group
- raw prerequisite information

Result:

PASS

No Course duplication is required across Study Plans.

---

# Test 10 — Plan-Specific Credit Hours

Credit hours are stored on:

Study Plan Course

not:

Course

Reason:

Morshidi must preserve the value published inside each specific
curriculum version.

Result:

PASS

---

# Test 11 — Single Prerequisite

Course:

1501112 — برمجة الحاسوب (2)

Published prerequisite:

1501110

Raw value:

1501110

Expected representation:

Study Plan Course
└── raw_prerequisite_text: 1501110

Course Dependency Group 1
├── dependency_type: prerequisite
└── Course Dependency Option
    └── 1501110

Result:

PASS

---

# Test 12 — Multiple Prerequisite References

Course:

1505311 — تعلم الآلة

Published prerequisite value:

1505101,1505201

Raw value must remain:

1505101,1505201

Structured representation can contain:

Dependency Group 1
└── 1505101

Dependency Group 2
└── 1505201

However:

The structured logical interpretation must only be marked:

prerequisite_logic_status = verified

when the university's intended logic has been confirmed.

Until then:

prerequisite_logic_status = unresolved

is valid.

Result:

PASS

The model preserves the official value without forcing an
unverified logical assumption.

---

# Test 13 — Referenced-Only Dependency Course

Course:

1505320 — تعلم الآلة المتقدم

Published prerequisite value:

0300103,1505311

Problem:

0300103 is referenced officially but does not appear as a selectable
Plan 12 Course in the extracted dataset.

Expected representation:

Course:

0300103

catalog_status:

referenced_only

Dependency structure may reference Course 0300103 normally.

Raw value remains:

0300103,1505311

Morshidi must NOT automatically replace it with 0300104.

Result:

PASS

---

# Test 14 — Second Referenced-Only Dependency Course

Course:

1505366 — معالجة الصور الرقمية

Published prerequisite value:

0301241,1505101

Expected referenced Course:

0301241

catalog_status:

referenced_only

Morshidi must NOT automatically replace it with 0301245.

Result:

PASS

---

# Test 15 — All External Dependency References

Current prerequisite codes referenced outside the selectable
Plan 12 Course list:

- 0200150
- 0201001
- 0200151
- 0202001
- 0300103
- 0301241

Expected behavior:

Each code may exist as:

Course

with:

catalog_status = referenced_only

until additional official information is verified.

Result:

PASS

---

# Test 16 — Multi-Level Dependency Chain

Course:

1505461 — الرؤية الحاسوبية

Published prerequisite references:

1505366,1505415

Dependencies themselves have additional dependencies.

Example:

1505461
├── 1505366
│   ├── 0301241
│   └── 1505101
│
└── 1505415
    └── 1505311

Expected behavior:

Morshidi represents each relationship independently.

The Rules Engine later traverses the dependency graph.

No Course-specific chain is hardcoded.

Result:

PASS

---

# Test 17 — Corequisite Extensibility

Plan 12 data currently focuses on prerequisite references.

The model must still support future rules such as:

Course X requires Course Y concurrently.

Expected structure:

Course Dependency Group
└── dependency_type: corequisite

No database redesign should be required.

Result:

PASS

The generic Course Dependency model supports both:

- prerequisite
- corequisite

---

# Test 18 — Elective Requirement Group

Requirement Group:

UNIVERSITY_ELECTIVE

Required Credit Hours:

9

Available Course Records:

11

Available Course Hours:

33

Expected behavior:

The Student does NOT need all 33 hours.

The Requirement Group is satisfied when applicable completion rules
reach the required 9 hours.

Result:

PASS

---

# Test 19 — Major Elective Requirement Group

Requirement Group:

MAJOR_ELECTIVE

Required Credit Hours:

9

Available Course Records:

13

Available Course Hours:

39

Expected behavior:

39 represents available options.

9 represents the graduation requirement.

Result:

PASS

---

# Test 20 — Raw Academic Data Preservation

Example:

1505320 — تعلم الآلة المتقدم

Published raw prerequisite:

0300103,1505311

Morshidi may later create structured Dependency records.

However:

raw_prerequisite_text must remain unchanged.

Architecture:

Official Source
↓
raw_prerequisite_text
↓
Structured Dependency Data
↓
Rules Engine

Result:

PASS

---

# Test 21 — Unverified Prerequisite Logic

The official source may provide multiple Course codes without enough
information to prove the exact logical expression.

Example:

0300103,1505311

Morshidi must NOT claim:

A AND B

or:

A OR B

unless the interpretation has sufficient official support.

Expected status:

prerequisite_logic_status:

unresolved

Raw source data remains preserved.

Result:

PASS

This prevents academic rules from being invented during ingestion.

---

# Test 22 — Course Equivalency Safety

Potential unresolved relationships:

0300103 ↔ 0300104

0301241 ↔ 0301245

Expected behavior:

No verified Course Equivalency is created without official evidence.

Result:

PASS

---

# Test 23 — Directional Replacement

Future example:

Old Course A

is replaced by:

New Course B

Expected representation:

source_course_id:

A

target_course_id:

B

relationship_type:

replacement

is_bidirectional:

false

This must NOT automatically imply:

B replaced by A

Result:

PASS

---

# Test 24 — Bidirectional Equivalency

Future official example:

Course A and Course B are officially equivalent.

Expected representation:

relationship_type:

equivalent

is_bidirectional:

true

Result:

PASS

The model distinguishes equivalency from replacement.

---

# Test 25 — Academic Source Traceability

Important records can reference an Academic Source.

Expected relationships:

Study Plan
→ Academic Source

Study Plan Course
→ Academic Source

Course Equivalency
→ Academic Source

Result:

PASS

---

# Test 26 — Source Snapshot Support

Official webpages can change.

Academic Source supports:

- source_url
- retrieved_at
- snapshot_ref
- content_hash

Therefore Morshidi can later retain evidence of what was
actually used during ingestion.

Result:

PASS

---

# Test 27 — Duplicate Course Protection

The same Course must not accidentally appear twice in one Study Plan.

Conceptual uniqueness:

study_plan_id + course_id

Example:

1505320 appeared at the boundary of two screenshots during Phase 1.

It must remain one Study Plan Course.

Result:

PASS

---

# Test 28 — Course Identity Constraint

Conceptual Course uniqueness:

university_id + course_code

Example:

Zarqa University
+
1505311

identifies one Course.

Result:

PASS

---

# Test 29 — Requirement Group Identity Constraint

Conceptual uniqueness:

study_plan_id + group_code

Example:

Plan 12
+
MAJOR_REQUIRED

must identify one Requirement Group.

Result:

PASS

---

# Test 30 — Self Dependency Protection

Invalid future structure:

Course X
↓
depends on
Course X

Expected behavior:

The future database must reject accidental self-dependencies.

Result:

PASS

The integrity requirement is documented in Model Version 2.0.

---

# Test 31 — Learning Type

Plan 12 contains learning-type values such as:

- نظري
- عملي
- التعلم القائم على المشاريع

Expected location:

Study Plan Course.learning_type

Result:

PASS

---

# Test 32 — Delivery Mode

Plan 12 contains delivery values such as:

- وجاهي
- مدمج
- الكتروني

Expected location:

Study Plan Course.delivery_mode

Result:

PASS

---

# Test 33 — Arabic Canonical Data

The current official Study Plan is Arabic.

Expected behavior:

name_ar contains the verified official Course name.

name_en may remain null.

Morshidi must not present an unofficial English translation
as official University data.

Result:

PASS

---

# Dataset-Level Validation

Total extracted Study Plan records:

68

Required Graduation Hours:

132

Zero-credit Study Plan Courses:

2

Selectable Requirement Groups:

6

External prerequisite Course references:

6

Records structurally representable by Model Version 2.0:

68 / 68

Result:

PASS

---

# Requirement Group Validation

## UNIVERSITY_REQUIRED

Required Hours:

18

Extracted Hours:

18

Result:

PASS

---

## UNIVERSITY_ELECTIVE

Required Hours:

9

Available Hours:

33

Result:

PASS

---

## FACULTY_REQUIRED

Required Hours:

21

Extracted Hours:

21

Result:

PASS

---

## SUPPORTING_REQUIRED

Required Hours:

12

Extracted Hours:

12

Result:

PASS

---

## MAJOR_REQUIRED

Required Hours:

63

Extracted Hours:

63

Result:

PASS

---

## MAJOR_ELECTIVE

Required Hours:

9

Available Hours:

39

Result:

PASS

---

# Validation Findings

Academic Data Model Version 2.0 can structurally represent:

- University hierarchy
- Faculties
- Majors
- Study Plan versions
- Requirement Groups
- stable group codes
- requirement scope
- required vs elective behavior
- shared Courses
- Plan-specific Course properties
- zero-credit Courses
- raw prerequisite values
- structured dependencies
- prerequisites
- future corequisites
- referenced-only Courses
- multi-level dependency chains
- unresolved prerequisite logic
- Course equivalencies
- directional replacements
- source traceability
- source snapshots
- Arabic canonical academic data

No Phase 1 record requires Course-specific hardcoded application logic.

---

# Explicitly Unresolved Academic Questions

The following are DATA questions, not Data Model failures.

## 1. Course relationship

0300103 ↔ 0300104

Status:

UNRESOLVED

---

## 2. Course relationship

0301241 ↔ 0301245

Status:

UNRESOLVED

---

## 3. Multiple prerequisite logical interpretation

Comma-separated prerequisite values exist in the official source.

The exact logical interpretation must not be treated as verified
without sufficient academic evidence.

Until verified:

raw_prerequisite_text is authoritative.

prerequisite_logic_status may remain:

unresolved

These open academic questions do NOT require redesigning the
Academic Data Model.

---

# Out of Scope for Phase 2

The following are intentionally NOT modeled in detail yet:

- Student accounts
- Student completed Courses
- grades
- passed / failed status
- repeated Courses
- withdrawals
- transferred Courses
- GPA
- semester load limits
- graduation eligibility
- recommendation scoring
- AI Advisor behavior

These belong to later development phases.

Their absence does NOT block approval of the Academic Catalog Model.

---

# Phase 2 Final Checklist

[x] University entity validated

[x] Faculty entity validated

[x] Major entity validated

[x] Study Plan versioning validated

[x] Requirement Group model validated

[x] stable group_code validated

[x] scope and requirement_type separation validated

[x] Course identity model validated

[x] Course / Study Plan Course separation validated

[x] Plan-specific credit hours validated

[x] zero-credit Courses validated

[x] raw prerequisite preservation validated

[x] generic Dependency model validated

[x] prerequisite support validated

[x] future corequisite support validated

[x] referenced-only Courses validated

[x] multi-level dependencies validated

[x] unresolved dependency logic safely represented

[x] Course Equivalency model validated

[x] Equivalency directionality validated

[x] Academic Source model validated

[x] source snapshot architecture validated

[x] database integrity requirements validated conceptually

[x] Arabic canonical-data rule validated

[x] elective pools validated

[x] all 68 Phase 1 records structurally representable

[x] final Academic Data Model review completed

[ ] Final approval

---

# Phase 2 Status

PHASE 2 STATUS:

AWAITING FINAL APPROVAL

Academic Data Model Version:

2.0

Structural Validation:

PASSED

Dataset Validation:

68 / 68 RECORDS REPRESENTABLE

Database Implementation:

NOT STARTED

Next Action:

Perform final approval of Phase 2.

Only after approval may Phase 3 begin.