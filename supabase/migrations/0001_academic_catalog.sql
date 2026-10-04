-- Morshidi Phase 4.1 draft: academic catalog schema only.
-- Review this migration before applying it to any Supabase project.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table public.universities (
  id uuid primary key default gen_random_uuid(),
  name_ar text not null check (btrim(name_ar) <> ''),
  name_en text check (name_en is null or btrim(name_en) <> ''),
  country text not null check (btrim(country) <> ''),
  website text check (website is null or btrim(website) <> ''),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.faculties (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references public.universities(id) on delete restrict,
  code text check (code is null or btrim(code) <> ''),
  name_ar text not null check (btrim(name_ar) <> ''),
  name_en text check (name_en is null or btrim(name_en) <> ''),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.majors (
  id uuid primary key default gen_random_uuid(),
  faculty_id uuid not null references public.faculties(id) on delete restrict,
  code text check (code is null or btrim(code) <> ''),
  name_ar text not null check (btrim(name_ar) <> ''),
  name_en text check (name_en is null or btrim(name_en) <> ''),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.academic_sources (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references public.universities(id) on delete restrict,
  source_type text not null check (source_type in (
    'official_webpage', 'official_pdf', 'official_study_plan',
    'university_regulation', 'university_course_catalog', 'manual_verification'
  )),
  source_url text check (source_url is null or btrim(source_url) <> ''),
  title text not null check (btrim(title) <> ''),
  retrieved_at timestamptz,
  plan_number text check (plan_number is null or btrim(plan_number) <> ''),
  source_status text not null default 'unknown' check (source_status in (
    'active', 'archived', 'unavailable', 'unknown'
  )),
  snapshot_ref text check (snapshot_ref is null or btrim(snapshot_ref) <> ''),
  content_hash text check (content_hash is null or btrim(content_hash) <> ''),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.study_plans (
  id uuid primary key default gen_random_uuid(),
  major_id uuid not null references public.majors(id) on delete restrict,
  plan_number text not null check (btrim(plan_number) <> ''),
  total_credit_hours numeric(6, 2) not null check (total_credit_hours >= 0),
  effective_year smallint check (effective_year is null or effective_year between 1900 and 9999),
  status text not null default 'unknown' check (status in ('active', 'archived', 'draft', 'unknown')),
  source_id uuid references public.academic_sources(id) on delete restrict,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Treat a missing effective year as one distinct identity value rather than
-- allowing duplicate undated versions of the same major and plan number.
create unique index uq_study_plans_major_plan_effective_year
  on public.study_plans (major_id, plan_number, coalesce(effective_year, -1));

create table public.requirement_groups (
  id uuid primary key default gen_random_uuid(),
  study_plan_id uuid not null references public.study_plans(id) on delete restrict,
  group_code text not null check (btrim(group_code) <> ''),
  name_ar text not null check (btrim(name_ar) <> ''),
  name_en text check (name_en is null or btrim(name_en) <> ''),
  scope text not null check (scope in ('university', 'faculty', 'major', 'supporting', 'other')),
  requirement_type text not null check (requirement_type in ('required', 'elective')),
  required_credit_hours numeric(6, 2) not null check (required_credit_hours >= 0),
  minimum_courses integer check (minimum_courses is null or minimum_courses >= 0),
  maximum_courses integer check (maximum_courses is null or maximum_courses >= 0),
  display_order integer not null default 0 check (display_order >= 0),
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (study_plan_id, group_code),
  unique (id, study_plan_id),
  check (maximum_courses is null or minimum_courses is null or maximum_courses >= minimum_courses)
);

create table public.courses (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references public.universities(id) on delete restrict,
  course_code text not null check (btrim(course_code) <> ''),
  name_ar text check (name_ar is null or btrim(name_ar) <> ''),
  name_en text check (name_en is null or btrim(name_en) <> ''),
  catalog_status text not null default 'unknown' check (catalog_status in (
    'known', 'referenced_only', 'legacy', 'unknown'
  )),
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (university_id, course_code),
  unique (id, university_id),
  check (catalog_status <> 'known' or name_ar is not null or name_en is not null)
);

create table public.study_plan_courses (
  id uuid primary key default gen_random_uuid(),
  study_plan_id uuid not null references public.study_plans(id) on delete restrict,
  course_id uuid not null references public.courses(id) on delete restrict,
  requirement_group_id uuid not null,
  credit_hours numeric(6, 2) not null check (credit_hours >= 0),
  learning_type text check (learning_type is null or btrim(learning_type) <> ''),
  delivery_mode text check (delivery_mode is null or btrim(delivery_mode) <> ''),
  raw_prerequisite_text text,
  prerequisite_logic_status text not null default 'not_applicable' check (prerequisite_logic_status in (
    'not_applicable', 'verified', 'unresolved', 'source_conflict'
  )),
  verification_status text not null default 'needs_review' check (verification_status in (
    'verified', 'needs_review', 'unresolved', 'source_conflict'
  )),
  source_id uuid references public.academic_sources(id) on delete restrict,
  display_order integer not null default 0 check (display_order >= 0),
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (study_plan_id, course_id),
  foreign key (requirement_group_id, study_plan_id)
    references public.requirement_groups (id, study_plan_id) on delete restrict
);

create table public.course_dependency_groups (
  id uuid primary key default gen_random_uuid(),
  study_plan_course_id uuid not null references public.study_plan_courses(id) on delete cascade,
  dependency_type text not null check (dependency_type in ('prerequisite', 'corequisite')),
  group_number integer not null check (group_number > 0),
  verification_status text not null default 'unresolved' check (verification_status in (
    'verified', 'unresolved', 'source_conflict'
  )),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (study_plan_course_id, dependency_type, group_number)
);

create table public.course_dependency_options (
  id uuid primary key default gen_random_uuid(),
  dependency_group_id uuid not null references public.course_dependency_groups(id) on delete cascade,
  dependency_course_id uuid not null references public.courses(id) on delete restrict,
  minimum_grade text check (minimum_grade is null or btrim(minimum_grade) <> ''),
  verification_status text not null default 'unresolved' check (verification_status in (
    'verified', 'referenced_only', 'unresolved', 'source_conflict'
  )),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (dependency_group_id, dependency_course_id)
);

create table public.course_equivalencies (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references public.universities(id) on delete restrict,
  source_course_id uuid not null,
  target_course_id uuid not null,
  relationship_type text not null check (relationship_type in ('equivalent', 'replacement', 'legacy_code')),
  is_bidirectional boolean not null default false,
  effective_from date,
  effective_to date,
  source_id uuid references public.academic_sources(id) on delete restrict,
  verification_status text not null default 'pending' check (verification_status in (
    'verified', 'pending', 'unresolved', 'rejected'
  )),
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (source_course_id <> target_course_id),
  check (effective_to is null or effective_from is null or effective_to >= effective_from),
  foreign key (source_course_id, university_id)
    references public.courses (id, university_id) on delete restrict,
  foreign key (target_course_id, university_id)
    references public.courses (id, university_id) on delete restrict
);

create index idx_faculties_university_id on public.faculties (university_id);
create index idx_majors_faculty_id on public.majors (faculty_id);
create index idx_academic_sources_university_status on public.academic_sources (university_id, source_status);
create index idx_study_plans_major_id on public.study_plans (major_id);
create index idx_study_plans_source_id on public.study_plans (source_id);
create index idx_courses_course_code on public.courses (course_code);
create index idx_study_plan_courses_requirement_group_id
  on public.study_plan_courses (requirement_group_id);
create index idx_study_plan_courses_source_id on public.study_plan_courses (source_id);
create index idx_course_dependency_options_dependency_course_id
  on public.course_dependency_options (dependency_course_id);
create index idx_course_equivalencies_source_course_id on public.course_equivalencies (source_course_id);
create index idx_course_equivalencies_target_course_id on public.course_equivalencies (target_course_id);
create index idx_course_equivalencies_source_id on public.course_equivalencies (source_id);
create unique index uq_course_equivalencies_identity
  on public.course_equivalencies (
    university_id,
    source_course_id,
    target_course_id,
    relationship_type,
    effective_from,
    effective_to
  ) nulls not distinct;

create or replace function public.validate_study_plan_course_university()
returns trigger
language plpgsql
as $$
begin
  if not exists (
    select 1
    from public.study_plans study_plan
    join public.majors major on major.id = study_plan.major_id
    join public.faculties faculty on faculty.id = major.faculty_id
    join public.courses course on course.id = new.course_id
    where study_plan.id = new.study_plan_id
      and faculty.university_id = course.university_id
  ) then
    raise exception 'Study plan course must belong to the study plan university';
  end if;

  if new.source_id is not null and not exists (
    select 1
    from public.study_plans study_plan
    join public.majors major on major.id = study_plan.major_id
    join public.faculties faculty on faculty.id = major.faculty_id
    join public.academic_sources source on source.id = new.source_id
    where study_plan.id = new.study_plan_id
      and faculty.university_id = source.university_id
  ) then
    raise exception 'Study plan course source must belong to the study plan university';
  end if;

  return new;
end;
$$;

create or replace function public.validate_study_plan_source_university()
returns trigger
language plpgsql
as $$
begin
  if new.source_id is not null and not exists (
    select 1
    from public.majors major
    join public.faculties faculty on faculty.id = major.faculty_id
    join public.academic_sources source on source.id = new.source_id
    where major.id = new.major_id
      and faculty.university_id = source.university_id
  ) then
    raise exception 'Study plan source must belong to the study plan university';
  end if;
  return new;
end;
$$;

create or replace function public.validate_dependency_course_university()
returns trigger
language plpgsql
as $$
begin
  if tg_table_name = 'course_dependency_options' then
    if not exists (
      select 1
      from public.course_dependency_groups dependency_group
      join public.study_plan_courses plan_course
        on plan_course.id = dependency_group.study_plan_course_id
      join public.study_plans study_plan on study_plan.id = plan_course.study_plan_id
      join public.majors major on major.id = study_plan.major_id
      join public.faculties faculty on faculty.id = major.faculty_id
      join public.courses dependency_course on dependency_course.id = new.dependency_course_id
      where dependency_group.id = new.dependency_group_id
        and faculty.university_id = dependency_course.university_id
    ) then
      raise exception 'Dependency course must belong to the parent study plan course university';
    end if;
  elsif tg_table_name = 'course_dependency_groups' then
    if exists (
      select 1
      from public.study_plan_courses plan_course
      join public.study_plans study_plan on study_plan.id = plan_course.study_plan_id
      join public.majors major on major.id = study_plan.major_id
      join public.faculties faculty on faculty.id = major.faculty_id
      join public.course_dependency_options dependency_option
        on dependency_option.dependency_group_id = new.id
      join public.courses dependency_course on dependency_course.id = dependency_option.dependency_course_id
      where plan_course.id = new.study_plan_course_id
        and faculty.university_id <> dependency_course.university_id
    ) then
      raise exception 'Dependency group cannot be moved across university boundaries';
    end if;
  end if;
  return new;
end;
$$;

create or replace function public.validate_course_equivalency_source_university()
returns trigger
language plpgsql
as $$
begin
  if new.source_id is not null and not exists (
    select 1
    from public.academic_sources source
    where source.id = new.source_id
      and source.university_id = new.university_id
  ) then
    raise exception 'Course equivalency source must belong to the equivalency university';
  end if;
  return new;
end;
$$;

create or replace function public.prevent_referenced_source_university_change()
returns trigger
language plpgsql
as $$
begin
  if exists (
    select 1 from public.study_plans where source_id = new.id
    union all
    select 1 from public.study_plan_courses where source_id = new.id
    union all
    select 1 from public.course_equivalencies where source_id = new.id
  ) then
    raise exception 'Cannot change an academic source university while the source is referenced';
  end if;
  return new;
end;
$$;

create or replace function public.prevent_populated_catalog_ownership_change()
returns trigger
language plpgsql
as $$
begin
  if tg_table_name = 'faculties' and exists (
    select 1 from public.majors where faculty_id = new.id
  ) then
    raise exception 'Cannot change a faculty university while the faculty has majors';
  elsif tg_table_name = 'majors' and exists (
    select 1 from public.study_plans where major_id = new.id
  ) then
    raise exception 'Cannot move a major while it has study plans';
  elsif tg_table_name = 'study_plans' and exists (
    select 1 from public.study_plan_courses where study_plan_id = new.id
  ) then
    raise exception 'Cannot move a study plan while it has study plan courses';
  elsif tg_table_name = 'courses' and exists (
    select 1 from public.study_plan_courses where course_id = new.id
    union all
    select 1 from public.course_dependency_options where dependency_course_id = new.id
    union all
    select 1 from public.course_equivalencies
      where source_course_id = new.id or target_course_id = new.id
  ) then
    raise exception 'Cannot change a course university while the course is referenced';
  end if;
  return new;
end;
$$;

create or replace function public.prevent_self_course_dependency()
returns trigger
language plpgsql
as $$
begin
  if tg_table_name = 'course_dependency_options' then
    if exists (
      select 1
      from public.course_dependency_groups dependency_group
      join public.study_plan_courses plan_course
        on plan_course.id = dependency_group.study_plan_course_id
      where dependency_group.id = new.dependency_group_id
        and plan_course.course_id = new.dependency_course_id
    ) then
      raise exception 'A course cannot depend on itself';
    end if;
  elsif tg_table_name = 'course_dependency_groups' then
    if exists (
      select 1
      from public.study_plan_courses plan_course
      join public.course_dependency_options dependency_option
        on dependency_option.dependency_group_id = new.id
      where plan_course.id = new.study_plan_course_id
        and plan_course.course_id = dependency_option.dependency_course_id
    ) then
      raise exception 'A dependency group cannot be moved to its own dependency';
    end if;
  elsif tg_table_name = 'study_plan_courses' then
    if exists (
      select 1
      from public.course_dependency_groups dependency_group
      join public.course_dependency_options dependency_option
        on dependency_option.dependency_group_id = dependency_group.id
      where dependency_group.study_plan_course_id = new.id
        and dependency_option.dependency_course_id = new.course_id
    ) then
      raise exception 'A course cannot be changed to its own dependency';
    end if;
  end if;
  return new;
end;
$$;

create trigger prevent_self_course_dependency_on_option
before insert or update of dependency_group_id, dependency_course_id on public.course_dependency_options
for each row execute function public.prevent_self_course_dependency();

create trigger prevent_self_course_dependency_on_plan_course
before update of course_id on public.study_plan_courses
for each row execute function public.prevent_self_course_dependency();

create trigger prevent_self_course_dependency_on_group
before update of study_plan_course_id on public.course_dependency_groups
for each row execute function public.prevent_self_course_dependency();

create trigger validate_study_plan_course_university_on_write
before insert or update of study_plan_id, course_id, source_id on public.study_plan_courses
for each row execute function public.validate_study_plan_course_university();

create trigger validate_study_plan_source_university_on_write
before insert or update of major_id, source_id on public.study_plans
for each row execute function public.validate_study_plan_source_university();

create trigger validate_dependency_course_university_on_option_write
before insert or update of dependency_group_id, dependency_course_id on public.course_dependency_options
for each row execute function public.validate_dependency_course_university();

create trigger validate_dependency_course_university_on_group_move
before update of study_plan_course_id on public.course_dependency_groups
for each row execute function public.validate_dependency_course_university();

create trigger validate_course_equivalency_source_university_on_write
before insert or update of university_id, source_id on public.course_equivalencies
for each row execute function public.validate_course_equivalency_source_university();

create trigger prevent_referenced_source_university_change_on_update
before update of university_id on public.academic_sources
for each row execute function public.prevent_referenced_source_university_change();

create trigger prevent_populated_faculty_university_change
before update of university_id on public.faculties
for each row execute function public.prevent_populated_catalog_ownership_change();

create trigger prevent_populated_major_faculty_change
before update of faculty_id on public.majors
for each row execute function public.prevent_populated_catalog_ownership_change();

create trigger prevent_populated_study_plan_major_change
before update of major_id on public.study_plans
for each row execute function public.prevent_populated_catalog_ownership_change();

create trigger prevent_referenced_course_university_change
before update of university_id on public.courses
for each row execute function public.prevent_populated_catalog_ownership_change();

create trigger set_universities_updated_at before update on public.universities
for each row execute function public.set_updated_at();
create trigger set_faculties_updated_at before update on public.faculties
for each row execute function public.set_updated_at();
create trigger set_majors_updated_at before update on public.majors
for each row execute function public.set_updated_at();
create trigger set_academic_sources_updated_at before update on public.academic_sources
for each row execute function public.set_updated_at();
create trigger set_study_plans_updated_at before update on public.study_plans
for each row execute function public.set_updated_at();
create trigger set_requirement_groups_updated_at before update on public.requirement_groups
for each row execute function public.set_updated_at();
create trigger set_courses_updated_at before update on public.courses
for each row execute function public.set_updated_at();
create trigger set_study_plan_courses_updated_at before update on public.study_plan_courses
for each row execute function public.set_updated_at();
create trigger set_course_dependency_groups_updated_at before update on public.course_dependency_groups
for each row execute function public.set_updated_at();
create trigger set_course_dependency_options_updated_at before update on public.course_dependency_options
for each row execute function public.set_updated_at();
create trigger set_course_equivalencies_updated_at before update on public.course_equivalencies
for each row execute function public.set_updated_at();

alter table public.universities enable row level security;
alter table public.faculties enable row level security;
alter table public.majors enable row level security;
alter table public.academic_sources enable row level security;
alter table public.study_plans enable row level security;
alter table public.requirement_groups enable row level security;
alter table public.courses enable row level security;
alter table public.study_plan_courses enable row level security;
alter table public.course_dependency_groups enable row level security;
alter table public.course_dependency_options enable row level security;
alter table public.course_equivalencies enable row level security;

revoke all on table public.universities from anon, authenticated;
revoke all on table public.faculties from anon, authenticated;
revoke all on table public.majors from anon, authenticated;
revoke all on table public.academic_sources from anon, authenticated;
revoke all on table public.study_plans from anon, authenticated;
revoke all on table public.requirement_groups from anon, authenticated;
revoke all on table public.courses from anon, authenticated;
revoke all on table public.study_plan_courses from anon, authenticated;
revoke all on table public.course_dependency_groups from anon, authenticated;
revoke all on table public.course_dependency_options from anon, authenticated;
revoke all on table public.course_equivalencies from anon, authenticated;

-- No RLS policies are created in Phase 4.1. End-user catalog access will be
-- explicitly designed later; backend/database-owner access is separate.
