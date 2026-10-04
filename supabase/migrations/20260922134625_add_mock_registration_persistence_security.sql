-- Phase P6.4: immutable Mock Registration persistence and security foundation.
-- Academic validation remains exclusively in the P6.2 domain engine.

create table public.mock_registration_target_periods (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references public.universities(id) on delete restrict,
  provider_namespace text not null check (btrim(provider_namespace) <> ''),
  period_key text not null check (btrim(period_key) <> ''),
  period_class text not null check (period_class in (
    'DECLARED_PLANNING_PERIOD',
    'OFFICIAL_PERIOD_REFERENCE',
    'SYNTHETIC_SANDBOX_PERIOD'
  )),
  verified_provider_source boolean not null default false,
  source_version text not null check (btrim(source_version) <> ''),
  is_expired boolean not null default false,
  expiration_source_version text check (
    expiration_source_version is null or btrim(expiration_source_version) <> ''
  ),
  expired_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (university_id, provider_namespace, period_key, source_version),
  unique (id, university_id),
  check (
    period_class <> 'OFFICIAL_PERIOD_REFERENCE'
    or verified_provider_source
  ),
  check (
    (not is_expired and expiration_source_version is null and expired_at is null)
    or (is_expired and expiration_source_version is not null and expired_at is not null)
  )
);

create table public.mock_registration_intent_revisions (
  id uuid primary key default gen_random_uuid(),
  intent_id uuid not null unique,
  owner_user_id uuid not null references auth.users(id) on delete restrict,
  university_id uuid not null references public.universities(id) on delete restrict,
  major_id uuid not null references public.majors(id) on delete restrict,
  study_plan_id uuid not null references public.study_plans(id) on delete restrict,
  study_plan_version text not null check (btrim(study_plan_version) <> ''),
  target_period_id uuid not null,
  revision integer not null check (revision > 0),
  lifecycle_status text not null check (lifecycle_status in (
    'SUBMITTED', 'WITHDRAWN', 'EXPIRED'
  )),
  validation_status text not null check (validation_status in (
    'VALID', 'REVIEW_REQUIRED'
  )),
  content_fingerprint text not null check (
    content_fingerprint ~ '^[0-9a-f]{64}$'
  ),
  intent_provenance text not null check (intent_provenance in (
    'DECLARED_STUDENT_INTENT',
    'SYNTHETIC_SANDBOX_INTENT',
    'INSTITUTIONAL_IMPORT'
  )),
  intent_source_version text not null check (btrim(intent_source_version) <> ''),
  validation_reason_codes text[] not null default '{}'::text[],
  catalog_source_versions text[] not null default '{}'::text[],
  prerequisite_source_versions text[] not null default '{}'::text[],
  progress_state_version text not null check (btrim(progress_state_version) <> ''),
  progress_state_reference text check (
    progress_state_reference is null or btrim(progress_state_reference) <> ''
  ),
  phase5_policy_version text not null check (btrim(phase5_policy_version) <> ''),
  phase6_policy_version text not null check (btrim(phase6_policy_version) <> ''),
  p6_contract_version text not null check (btrim(p6_contract_version) <> ''),
  target_period_source_version text not null check (
    btrim(target_period_source_version) <> ''
  ),
  transparency_notice_version text not null check (
    btrim(transparency_notice_version) <> ''
  ),
  transparency_acknowledged_at timestamptz not null default now(),
  actor_class text not null check (actor_class in (
    'STUDENT_AUTHENTICATED',
    'APPLICATION_SERVICE',
    'AUTHORIZED_PERIOD_AUTHORITY'
  )),
  created_at timestamptz not null default now(),
  foreign key (target_period_id, university_id)
    references public.mock_registration_target_periods (id, university_id)
    on delete restrict,
  unique (
    owner_user_id,
    university_id,
    major_id,
    study_plan_id,
    study_plan_version,
    target_period_id,
    revision
  ),
  unique (id, owner_user_id),
  check (
    validation_status <> 'REVIEW_REQUIRED'
    or lifecycle_status = 'SUBMITTED'
  ),
  check (
    validation_status <> 'REVIEW_REQUIRED'
    or cardinality(validation_reason_codes) > 0
  )
);

create table public.mock_registration_intent_courses (
  id uuid primary key default gen_random_uuid(),
  revision_id uuid not null references public.mock_registration_intent_revisions(id)
    on delete restrict,
  course_id uuid not null references public.courses(id) on delete restrict,
  course_code text not null check (btrim(course_code) <> ''),
  selection_order smallint not null check (selection_order between 1 and 10),
  created_at timestamptz not null default now(),
  unique (revision_id, course_id),
  unique (revision_id, course_code),
  unique (revision_id, selection_order)
);

create table public.institutional_memberships (
  id uuid primary key default gen_random_uuid(),
  subject_user_id uuid not null references auth.users(id) on delete restrict,
  university_id uuid not null references public.universities(id) on delete restrict,
  provider_namespace text not null check (btrim(provider_namespace) <> ''),
  role text not null check (role = 'INSTITUTIONAL_ANALYST'),
  active boolean not null default true,
  authority_source text not null check (btrim(authority_source) <> ''),
  authority_source_version text not null check (
    btrim(authority_source_version) <> ''
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (subject_user_id, university_id, provider_namespace, role)
);

create index idx_mock_registration_revisions_owner_key_revision
  on public.mock_registration_intent_revisions (
    owner_user_id,
    university_id,
    major_id,
    study_plan_id,
    study_plan_version,
    target_period_id,
    revision desc
  );

create index idx_mock_registration_revisions_university_period
  on public.mock_registration_intent_revisions (
    university_id,
    target_period_id,
    study_plan_id,
    revision desc
  );

create index idx_mock_registration_courses_revision
  on public.mock_registration_intent_courses (revision_id, selection_order);

create index idx_institutional_memberships_subject_university
  on public.institutional_memberships (subject_user_id, university_id)
  where active;

create or replace function public.validate_mock_registration_period_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.university_id is distinct from old.university_id
    or new.provider_namespace is distinct from old.provider_namespace
    or new.period_key is distinct from old.period_key
    or new.period_class is distinct from old.period_class
    or new.verified_provider_source is distinct from old.verified_provider_source
    or new.source_version is distinct from old.source_version then
    raise exception using
      errcode = '23514',
      message = 'Mock Registration target-period identity is immutable';
  end if;

  if old.is_expired and not new.is_expired then
    raise exception using
      errcode = '23514',
      message = 'Mock Registration target-period expiration cannot be reversed';
  end if;
  return new;
end;
$$;

create or replace function public.validate_mock_registration_revision_scope()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not exists (
    select 1
    from public.study_plans plan
    join public.majors major on major.id = plan.major_id
    join public.faculties faculty on faculty.id = major.faculty_id
    where plan.id = new.study_plan_id
      and major.id = new.major_id
      and faculty.university_id = new.university_id
  ) then
    raise exception using
      errcode = '23514',
      message = 'Mock Registration plan scope does not match its university and major';
  end if;

  if not exists (
    select 1
    from public.mock_registration_target_periods period
    where period.id = new.target_period_id
      and period.university_id = new.university_id
      and period.source_version = new.target_period_source_version
  ) then
    raise exception using
      errcode = '23514',
      message = 'Mock Registration target-period scope or source version does not match';
  end if;
  return new;
end;
$$;

create or replace function public.validate_mock_registration_course_scope()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  parent_plan_id uuid;
  parent_university_id uuid;
begin
  select revision.study_plan_id, revision.university_id
  into parent_plan_id, parent_university_id
  from public.mock_registration_intent_revisions revision
  where revision.id = new.revision_id;

  if parent_plan_id is null then
    raise exception using
      errcode = '23503',
      message = 'Mock Registration parent revision was not found';
  end if;

  if not exists (
    select 1
    from public.courses course
    join public.study_plan_courses plan_course
      on plan_course.course_id = course.id
    where course.id = new.course_id
      and course.university_id = parent_university_id
      and course.course_code = new.course_code
      and plan_course.study_plan_id = parent_plan_id
  ) then
    raise exception using
      errcode = '23514',
      message = 'Mock Registration course does not match the revision plan scope';
  end if;
  return new;
end;
$$;

create or replace function public.prevent_mock_registration_history_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception using
    errcode = '55000',
    message = 'Mock Registration history is immutable';
end;
$$;

create trigger validate_mock_registration_period_on_update
before update on public.mock_registration_target_periods
for each row execute function public.validate_mock_registration_period_update();

create trigger set_mock_registration_period_updated_at
before update on public.mock_registration_target_periods
for each row execute function public.set_updated_at();

create trigger validate_mock_registration_revision_scope_on_insert
before insert on public.mock_registration_intent_revisions
for each row execute function public.validate_mock_registration_revision_scope();

create trigger prevent_mock_registration_revision_update
before update on public.mock_registration_intent_revisions
for each row execute function public.prevent_mock_registration_history_mutation();

create trigger prevent_mock_registration_revision_delete
before delete on public.mock_registration_intent_revisions
for each row execute function public.prevent_mock_registration_history_mutation();

create trigger validate_mock_registration_course_scope_on_insert
before insert on public.mock_registration_intent_courses
for each row execute function public.validate_mock_registration_course_scope();

create trigger prevent_mock_registration_course_update
before update on public.mock_registration_intent_courses
for each row execute function public.prevent_mock_registration_history_mutation();

create trigger prevent_mock_registration_course_delete
before delete on public.mock_registration_intent_courses
for each row execute function public.prevent_mock_registration_history_mutation();

create trigger set_institutional_membership_updated_at
before update on public.institutional_memberships
for each row execute function public.set_updated_at();

create or replace function public.persist_mock_registration_revision(
  p_intent_id uuid,
  p_owner_user_id uuid,
  p_university_id uuid,
  p_major_id uuid,
  p_study_plan_id uuid,
  p_study_plan_version text,
  p_target_period_id uuid,
  p_expected_current_revision integer,
  p_lifecycle_status text,
  p_validation_status text,
  p_content_fingerprint text,
  p_intent_provenance text,
  p_intent_source_version text,
  p_validation_reason_codes text[],
  p_catalog_source_versions text[],
  p_prerequisite_source_versions text[],
  p_progress_state_version text,
  p_progress_state_reference text,
  p_phase5_policy_version text,
  p_phase6_policy_version text,
  p_p6_contract_version text,
  p_target_period_source_version text,
  p_transparency_notice_version text,
  p_actor_class text,
  p_course_ids uuid[],
  p_course_codes text[]
)
returns table (
  result_kind text,
  persisted_revision_id uuid,
  persisted_revision integer,
  persisted_fingerprint text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_revision integer;
  next_revision integer;
  existing_id uuid;
  existing_intent_id uuid;
  existing_fingerprint text;
  inserted_id uuid;
  course_count integer;
  course_index integer;
begin
  if p_expected_current_revision is not null and p_expected_current_revision < 1 then
    raise exception using errcode = '22023', message = 'expected_current_revision must be null or positive';
  end if;

  if p_lifecycle_status not in ('SUBMITTED', 'WITHDRAWN') then
    raise exception using errcode = '22023', message = 'Unsupported persistence lifecycle';
  end if;

  if p_validation_status not in ('VALID', 'REVIEW_REQUIRED')
    or (p_validation_status = 'REVIEW_REQUIRED' and p_lifecycle_status <> 'SUBMITTED') then
    raise exception using errcode = '22023', message = 'Unsupported persistence validation status';
  end if;

  if p_content_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception using errcode = '22023', message = 'Invalid content fingerprint shape';
  end if;

  if p_course_ids is null or p_course_codes is null
    or cardinality(p_course_ids) <> cardinality(p_course_codes) then
    raise exception using errcode = '22023', message = 'Course identity arrays must have equal cardinality';
  end if;

  course_count := cardinality(p_course_codes);
  if (p_lifecycle_status = 'SUBMITTED' and (course_count < 1 or course_count > 10))
    or (p_lifecycle_status = 'WITHDRAWN' and course_count <> 0) then
    raise exception using errcode = '22023', message = 'Course count does not match lifecycle';
  end if;

  if exists (
    select 1 from unnest(p_course_codes) code where code is null or btrim(code) = ''
  ) or cardinality(array(select distinct code from unnest(p_course_codes) code)) <> course_count
    or p_course_codes <> array(select code from unnest(p_course_codes) code order by code) then
    raise exception using errcode = '22023', message = 'Course codes must be unique canonical order';
  end if;

  if cardinality(array(select distinct course_id from unnest(p_course_ids) course_id)) <> course_count then
    raise exception using errcode = '22023', message = 'Course identifiers must be unique';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      concat_ws(
        chr(31),
        p_owner_user_id::text,
        p_university_id::text,
        p_major_id::text,
        p_study_plan_id::text,
        p_study_plan_version,
        p_target_period_id::text
      ),
      0
    )
  );

  next_revision := coalesce(p_expected_current_revision, 0) + 1;

  select revision.id, revision.intent_id, revision.content_fingerprint
  into existing_id, existing_intent_id, existing_fingerprint
  from public.mock_registration_intent_revisions revision
  where revision.owner_user_id = p_owner_user_id
    and revision.university_id = p_university_id
    and revision.major_id = p_major_id
    and revision.study_plan_id = p_study_plan_id
    and revision.study_plan_version = p_study_plan_version
    and revision.target_period_id = p_target_period_id
    and revision.revision = next_revision;

  if existing_id is not null then
    if existing_fingerprint = p_content_fingerprint then
      return query select 'IDEMPOTENT_REPLAY', existing_id, next_revision, existing_fingerprint;
    elsif existing_intent_id = p_intent_id then
      return query select 'PERSISTENCE_CONFLICT', existing_id, next_revision, existing_fingerprint;
    else
      return query select 'REVISION_CONFLICT', existing_id, next_revision, existing_fingerprint;
    end if;
    return;
  end if;

  select max(revision.revision)
  into current_revision
  from public.mock_registration_intent_revisions revision
  where revision.owner_user_id = p_owner_user_id
    and revision.university_id = p_university_id
    and revision.major_id = p_major_id
    and revision.study_plan_id = p_study_plan_id
    and revision.study_plan_version = p_study_plan_version
    and revision.target_period_id = p_target_period_id;

  if current_revision is distinct from p_expected_current_revision then
    return query select 'REVISION_CONFLICT', null::uuid, current_revision, null::text;
    return;
  end if;

  if exists (
    select 1
    from public.mock_registration_target_periods period
    where period.id = p_target_period_id
      and period.is_expired
  ) then
    raise exception using errcode = '23514', message = 'Mock Registration target period is expired';
  end if;

  insert into public.mock_registration_intent_revisions (
    intent_id,
    owner_user_id,
    university_id,
    major_id,
    study_plan_id,
    study_plan_version,
    target_period_id,
    revision,
    lifecycle_status,
    validation_status,
    content_fingerprint,
    intent_provenance,
    intent_source_version,
    validation_reason_codes,
    catalog_source_versions,
    prerequisite_source_versions,
    progress_state_version,
    progress_state_reference,
    phase5_policy_version,
    phase6_policy_version,
    p6_contract_version,
    target_period_source_version,
    transparency_notice_version,
    actor_class
  ) values (
    p_intent_id,
    p_owner_user_id,
    p_university_id,
    p_major_id,
    p_study_plan_id,
    p_study_plan_version,
    p_target_period_id,
    next_revision,
    p_lifecycle_status,
    p_validation_status,
    p_content_fingerprint,
    p_intent_provenance,
    p_intent_source_version,
    coalesce(p_validation_reason_codes, '{}'::text[]),
    coalesce(p_catalog_source_versions, '{}'::text[]),
    coalesce(p_prerequisite_source_versions, '{}'::text[]),
    p_progress_state_version,
    p_progress_state_reference,
    p_phase5_policy_version,
    p_phase6_policy_version,
    p_p6_contract_version,
    p_target_period_source_version,
    p_transparency_notice_version,
    p_actor_class
  ) returning id into inserted_id;

  for course_index in 1..course_count loop
    insert into public.mock_registration_intent_courses (
      revision_id,
      course_id,
      course_code,
      selection_order
    ) values (
      inserted_id,
      p_course_ids[course_index],
      p_course_codes[course_index],
      course_index
    );
  end loop;

  return query select 'INSERTED', inserted_id, next_revision, p_content_fingerprint;
end;
$$;

alter table public.mock_registration_target_periods enable row level security;
alter table public.mock_registration_intent_revisions enable row level security;
alter table public.mock_registration_intent_courses enable row level security;
alter table public.institutional_memberships enable row level security;

revoke all on table public.mock_registration_target_periods
  from public, anon, authenticated, service_role;
revoke all on table public.mock_registration_intent_revisions
  from public, anon, authenticated, service_role;
revoke all on table public.mock_registration_intent_courses
  from public, anon, authenticated, service_role;
revoke all on table public.institutional_memberships
  from public, anon, authenticated, service_role;

grant select on table public.mock_registration_intent_revisions to authenticated;
grant select on table public.mock_registration_intent_courses to authenticated;

grant select, insert, update on table public.mock_registration_target_periods to service_role;
grant select on table public.mock_registration_intent_revisions to service_role;
grant select on table public.mock_registration_intent_courses to service_role;
grant select, insert, update, delete on table public.institutional_memberships to service_role;

create policy "Users can select their own Mock Registration revisions"
on public.mock_registration_intent_revisions
for select
to authenticated
using ((select auth.uid()) = owner_user_id);

create policy "Users can select their own Mock Registration courses"
on public.mock_registration_intent_courses
for select
to authenticated
using (
  exists (
    select 1
    from public.mock_registration_intent_revisions revision
    where revision.id = revision_id
      and revision.owner_user_id = (select auth.uid())
  )
);

revoke execute on function public.persist_mock_registration_revision(
  uuid, uuid, uuid, uuid, uuid, text, uuid, integer, text, text, text, text,
  text, text[], text[], text[], text, text, text, text, text, text, text,
  text, uuid[], text[]
) from public, anon, authenticated;

grant execute on function public.persist_mock_registration_revision(
  uuid, uuid, uuid, uuid, uuid, text, uuid, integer, text, text, text, text,
  text, text[], text[], text[], text, text, text, text, text, text, text,
  text, uuid[], text[]
) to service_role;

revoke execute on function public.validate_mock_registration_period_update()
  from public, anon, authenticated;
revoke execute on function public.validate_mock_registration_revision_scope()
  from public, anon, authenticated;
revoke execute on function public.validate_mock_registration_course_scope()
  from public, anon, authenticated;
revoke execute on function public.prevent_mock_registration_history_mutation()
  from public, anon, authenticated;

comment on table public.mock_registration_target_periods is
  'P6.4 institution-scoped target-period authority; expiration is explicit and never clock-inferred.';
comment on table public.mock_registration_intent_revisions is
  'P6.4 immutable non-binding Mock Registration revision headers; not official enrollment.';
comment on table public.mock_registration_intent_courses is
  'P6.4 normalized immutable canonical course selections for one revision.';
comment on table public.institutional_memberships is
  'P6.4 server-authoritative minimum institutional analyst membership foundation.';
