-- Phase 6.2: private, user-owned student academic state.

create table public.student_academic_profiles (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  study_plan_id uuid not null references public.study_plans(id) on delete restrict,
  reported_cumulative_gpa numeric(6, 3),
  reported_gpa_scale numeric(6, 3),
  reported_earned_credit_hours numeric(7, 2),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner_user_id),
  check (reported_cumulative_gpa is null or reported_cumulative_gpa >= 0),
  check (reported_gpa_scale is null or reported_gpa_scale > 0),
  check (
    (reported_cumulative_gpa is null and reported_gpa_scale is null)
    or (reported_cumulative_gpa is not null and reported_gpa_scale is not null)
  ),
  check (
    reported_earned_credit_hours is null
    or reported_earned_credit_hours >= 0
  )
);

create table public.student_course_attempts (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.student_academic_profiles(id) on delete cascade,
  course_id uuid not null references public.courses(id) on delete restrict,
  outcome text not null check (outcome in (
    'PASSED', 'FAILED', 'IN_PROGRESS', 'WITHDRAWN'
  )),
  attempt_sequence integer check (
    attempt_sequence is null or attempt_sequence > 0
  ),
  term_label text check (term_label is null or btrim(term_label) <> ''),
  attempted_on date,
  reported_grade_text text check (
    reported_grade_text is null or btrim(reported_grade_text) <> ''
  ),
  record_source text not null default 'manual_entry' check (record_source in (
    'manual_entry', 'transcript_import', 'university_integration', 'admin_correction'
  )),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, course_id, attempt_sequence)
);

create index idx_student_academic_profiles_study_plan_id
  on public.student_academic_profiles (study_plan_id);
create index idx_student_course_attempts_profile_id
  on public.student_course_attempts (profile_id);
create index idx_student_course_attempts_course_id
  on public.student_course_attempts (course_id);
create index idx_student_course_attempts_profile_course_id
  on public.student_course_attempts (profile_id, course_id);
create index idx_student_course_attempts_profile_outcome
  on public.student_course_attempts (profile_id, outcome);

create or replace function public.validate_student_attempt_course_university()
returns trigger
language plpgsql
as $$
begin
  if not exists (select 1 from public.student_academic_profiles where id = new.profile_id)
    or not exists (select 1 from public.courses where id = new.course_id) then
    return new;
  end if;

  if not exists (
    select 1
    from public.student_academic_profiles profile
    join public.study_plans study_plan on study_plan.id = profile.study_plan_id
    join public.majors major on major.id = study_plan.major_id
    join public.faculties faculty on faculty.id = major.faculty_id
    join public.courses course on course.id = new.course_id
    where profile.id = new.profile_id
      and faculty.university_id = course.university_id
  ) then
    raise exception 'Student attempt course must belong to the profile study plan university';
  end if;
  return new;
end;
$$;

create or replace function public.prevent_student_profile_plan_change_with_attempts()
returns trigger
language plpgsql
as $$
begin
  if new.study_plan_id is distinct from old.study_plan_id
    and exists (
      select 1
      from public.student_course_attempts attempt
      where attempt.profile_id = new.id
    ) then
    raise exception 'Cannot change a student profile study plan while attempts exist';
  end if;
  return new;
end;
$$;

create or replace function public.prevent_student_attempt_course_university_change()
returns trigger
language plpgsql
as $$
begin
  if exists (
    select 1
    from public.student_course_attempts attempt
    join public.student_academic_profiles profile on profile.id = attempt.profile_id
    join public.study_plans study_plan on study_plan.id = profile.study_plan_id
    join public.majors major on major.id = study_plan.major_id
    join public.faculties faculty on faculty.id = major.faculty_id
    where attempt.course_id = new.id
      and faculty.university_id <> new.university_id
  ) then
    raise exception 'Cannot change a course university while student attempts reference it';
  end if;
  return new;
end;
$$;

create trigger validate_student_attempt_course_university_on_write
before insert or update of profile_id, course_id on public.student_course_attempts
for each row execute function public.validate_student_attempt_course_university();

create trigger prevent_student_profile_plan_change_on_update
before update of study_plan_id on public.student_academic_profiles
for each row execute function public.prevent_student_profile_plan_change_with_attempts();

create trigger prevent_student_attempt_course_university_change_on_update
before update of university_id on public.courses
for each row execute function public.prevent_student_attempt_course_university_change();

create trigger set_student_academic_profiles_updated_at
before update on public.student_academic_profiles
for each row execute function public.set_updated_at();

create trigger set_student_course_attempts_updated_at
before update on public.student_course_attempts
for each row execute function public.set_updated_at();

alter table public.student_academic_profiles enable row level security;
alter table public.student_course_attempts enable row level security;

revoke all on table public.student_academic_profiles from anon, authenticated;
revoke all on table public.student_course_attempts from anon, authenticated;
grant select, insert, update, delete on table public.student_academic_profiles to authenticated;
grant select, insert, update, delete on table public.student_course_attempts to authenticated;

create policy "Users can select their own academic profile"
on public.student_academic_profiles for select to authenticated
using ((select auth.uid()) = owner_user_id);

create policy "Users can insert their own academic profile"
on public.student_academic_profiles for insert to authenticated
with check ((select auth.uid()) = owner_user_id);

create policy "Users can update their own academic profile"
on public.student_academic_profiles for update to authenticated
using ((select auth.uid()) = owner_user_id)
with check ((select auth.uid()) = owner_user_id);

create policy "Users can delete their own academic profile"
on public.student_academic_profiles for delete to authenticated
using ((select auth.uid()) = owner_user_id);

create policy "Users can select their own course attempts"
on public.student_course_attempts for select to authenticated
using (
  exists (
    select 1
    from public.student_academic_profiles profile
    where profile.id = profile_id
      and profile.owner_user_id = (select auth.uid())
  )
);

create policy "Users can insert their own course attempts"
on public.student_course_attempts for insert to authenticated
with check (
  exists (
    select 1
    from public.student_academic_profiles profile
    where profile.id = profile_id
      and profile.owner_user_id = (select auth.uid())
  )
);

create policy "Users can update their own course attempts"
on public.student_course_attempts for update to authenticated
using (
  exists (
    select 1
    from public.student_academic_profiles profile
    where profile.id = profile_id
      and profile.owner_user_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1
    from public.student_academic_profiles profile
    where profile.id = profile_id
      and profile.owner_user_id = (select auth.uid())
  )
);

create policy "Users can delete their own course attempts"
on public.student_course_attempts for delete to authenticated
using (
  exists (
    select 1
    from public.student_academic_profiles profile
    where profile.id = profile_id
      and profile.owner_user_id = (select auth.uid())
  )
);
