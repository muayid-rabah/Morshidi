# Phase 6.2 student schema validation

Local Supabase validation covers the private profile and course-attempt schema.

| Check | Result |
| --- | --- |
| Clean local migration application | Pass |
| Student tables, foreign keys, indexes, functions, triggers, and RLS policies | Pass |
| Profile GPA/credit, one-profile, outcome, source, and attempt-sequence constraints | Defined and locally exercised during fixture validation |
| Same-university attempt protection and ownership-change protections | Defined in database triggers |
| Owner-scoped RLS | Pass: owner observed one profile/attempt; another authenticated user observed zero |
| Anon access | No grants or policies configured |

The final local database reset reapplies this migration from scratch and leaves
no synthetic test users or academic data.
