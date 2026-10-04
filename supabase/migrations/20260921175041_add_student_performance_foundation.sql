-- Phase P2: nullable raw performance facts only.  No grade policy, GPA, or
-- academic-period interpretation is encoded here.

alter table public.student_course_attempts
  add column raw_numeric_grade numeric,
  add column raw_letter_grade text,
  add column raw_grade_points numeric,
  add column raw_academic_year text,
  add column raw_term text,
  add column attempt_credit_hours numeric(7, 2),
  add column performance_provenance text not null default 'UNVERIFIED',
  add column performance_verification_state text not null default 'UNVERIFIED',
  add column performance_source_reference text,
  add constraint student_course_attempts_raw_letter_grade_nonblank
    check (raw_letter_grade is null or btrim(raw_letter_grade) <> ''),
  add constraint student_course_attempts_raw_academic_year_nonblank
    check (raw_academic_year is null or btrim(raw_academic_year) <> ''),
  add constraint student_course_attempts_raw_term_nonblank
    check (raw_term is null or btrim(raw_term) <> ''),
  add constraint student_course_attempts_attempt_credit_hours_nonnegative
    check (attempt_credit_hours is null or attempt_credit_hours >= 0),
  add constraint student_course_attempts_performance_provenance_allowed
    check (performance_provenance in (
      'OFFICIAL_VERIFIED', 'STUDENT_RECORD', 'DERIVED_DETERMINISTIC',
      'MODEL_OUTPUT', 'MANUAL_ACADEMIC_REVIEW', 'UNVERIFIED'
    )),
  add constraint student_course_attempts_performance_verification_state_allowed
    check (performance_verification_state in (
      'UNVERIFIED', 'VERIFIED', 'REVIEW_REQUIRED'
    )),
  add constraint student_course_attempts_performance_source_reference_nonblank
    check (
      performance_source_reference is null
      or btrim(performance_source_reference) <> ''
    ),
  add constraint student_course_attempts_official_verified_requires_verified_state
    check (
      performance_provenance <> 'OFFICIAL_VERIFIED'
      or performance_verification_state = 'VERIFIED'
    );

comment on column public.student_course_attempts.raw_numeric_grade is
  'Raw source value only; no range, scale, mapping, or outcome inference is applied.';
comment on column public.student_course_attempts.raw_letter_grade is
  'Raw source value only; no grade-policy interpretation is applied.';
comment on column public.student_course_attempts.raw_grade_points is
  'Raw source value only; no GPA calculation or reconciliation is applied.';
comment on column public.student_course_attempts.raw_academic_year is
  'Opaque supplied academic-year value; not a canonical or ordered period.';
comment on column public.student_course_attempts.raw_term is
  'Opaque supplied term value; not a canonical or ordered period.';
comment on column public.student_course_attempts.attempt_credit_hours is
  'Raw attempt credit value; distinct from catalog credits and not used for earned-credit logic.';

-- RLS still establishes ownership.  This trigger adds a column-level boundary
-- for direct authenticated clients while allowing trusted server/import paths
-- (which use a service-role key and have no auth.uid()) to write the facts.
create or replace function public.prevent_client_managed_performance_facts()
returns trigger
language plpgsql
as $$
begin
  if auth.uid() is null then
    return new;
  end if;

  if tg_op = 'INSERT' then
    if new.raw_numeric_grade is not null
      or new.raw_letter_grade is not null
      or new.raw_grade_points is not null
      or new.raw_academic_year is not null
      or new.raw_term is not null
      or new.attempt_credit_hours is not null
      or new.performance_provenance <> 'UNVERIFIED'
      or new.performance_verification_state <> 'UNVERIFIED'
      or new.performance_source_reference is not null then
      raise exception 'Performance facts are server/import managed';
    end if;
  elsif new.raw_numeric_grade is distinct from old.raw_numeric_grade
    or new.raw_letter_grade is distinct from old.raw_letter_grade
    or new.raw_grade_points is distinct from old.raw_grade_points
    or new.raw_academic_year is distinct from old.raw_academic_year
    or new.raw_term is distinct from old.raw_term
    or new.attempt_credit_hours is distinct from old.attempt_credit_hours
    or new.performance_provenance is distinct from old.performance_provenance
    or new.performance_verification_state is distinct from old.performance_verification_state
    or new.performance_source_reference is distinct from old.performance_source_reference then
    raise exception 'Performance facts are server/import managed';
  end if;
  return new;
end;
$$;

create trigger prevent_client_managed_performance_facts_on_write
before insert or update on public.student_course_attempts
for each row execute function public.prevent_client_managed_performance_facts();
