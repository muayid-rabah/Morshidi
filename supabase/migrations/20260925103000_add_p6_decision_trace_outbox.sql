-- P8 trusted-adapter foundation: durable outbox for persisted, non-binding P6 submits.
-- This migration creates pending source events only. It neither appends a P8 ledger
-- entry nor changes enrollment, academic standing, or deterministic P6 validation.

create table public.decision_trace_outbox (
  event_id uuid primary key,
  revision_id uuid not null unique references public.mock_registration_intent_revisions(id)
    on delete restrict,
  owner_user_id uuid not null references auth.users(id) on delete restrict,
  university_id uuid not null references public.universities(id) on delete restrict,
  major_id uuid not null references public.majors(id) on delete restrict,
  study_plan_id uuid not null references public.study_plans(id) on delete restrict,
  study_plan_version text not null check (btrim(study_plan_version) <> ''),
  target_period_id uuid not null references public.mock_registration_target_periods(id)
    on delete restrict,
  revision integer not null check (revision > 0),
  event_type text not null check (event_type = 'MOCK_REGISTRATION_SUBMIT'),
  snapshot_contract_version text not null check (snapshot_contract_version = '1.0'),
  source_snapshot jsonb not null,
  processing_state text not null default 'PENDING' check (processing_state in (
    'PENDING', 'PROCESSING', 'COMPLETED', 'PERMANENT_FAILURE'
  )),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  next_attempt_at timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  processing_started_at timestamptz,
  completed_at timestamptz,
  completed_ledger_integrity_hash text check (
    completed_ledger_integrity_hash is null
    or completed_ledger_integrity_hash ~ '^[0-9a-f]{64}$'
  ),
  last_error_class text check (last_error_class is null or last_error_class in (
    'TRANSIENT_P8_UNAVAILABLE', 'P8_DUPLICATE_MATCHED', 'P8_DUPLICATE_MISMATCH',
    'SOURCE_INTEGRITY_FAILURE', 'CONTRACT_FAILURE'
  )),
  last_error_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint decision_trace_outbox_event_matches_revision check (event_id = revision_id),
  constraint decision_trace_outbox_snapshot_object check (jsonb_typeof(source_snapshot) = 'object'),
  constraint decision_trace_outbox_snapshot_required_keys check (
    source_snapshot ?& array[
      'revision_id', 'intent_id', 'owner_user_id', 'university_id', 'major_id',
      'study_plan_id', 'study_plan_version', 'target_period_id', 'revision',
      'lifecycle_status', 'validation_status', 'content_fingerprint',
      'intent_provenance', 'intent_source_version', 'validation_reason_codes',
      'catalog_source_versions', 'prerequisite_source_versions',
      'progress_state_version', 'progress_state_reference', 'phase5_policy_version',
      'phase6_policy_version', 'p6_contract_version', 'target_period_source_version',
      'transparency_notice_version', 'actor_class', 'created_at', 'courses'
    ]
  ),
  constraint decision_trace_outbox_snapshot_identity_matches check (
    source_snapshot ->> 'revision_id' = revision_id::text
    and source_snapshot ->> 'owner_user_id' = owner_user_id::text
    and source_snapshot ->> 'university_id' = university_id::text
    and source_snapshot ->> 'study_plan_id' = study_plan_id::text
    and source_snapshot ->> 'target_period_id' = target_period_id::text
    and (source_snapshot ->> 'revision')::integer = revision
    and source_snapshot ->> 'lifecycle_status' = 'SUBMITTED'
  ),
  constraint decision_trace_outbox_operational_state check (
    (processing_state = 'PENDING'
      and lease_owner is null and lease_expires_at is null and processing_started_at is null
      and completed_at is null and completed_ledger_integrity_hash is null)
    or (processing_state = 'PROCESSING'
      and lease_owner is not null and btrim(lease_owner) <> '' and lease_expires_at is not null
      and processing_started_at is not null and completed_at is null
      and completed_ledger_integrity_hash is null)
    or (processing_state = 'COMPLETED'
      and lease_owner is null and lease_expires_at is null and completed_at is not null
      and completed_ledger_integrity_hash is not null)
    or (processing_state = 'PERMANENT_FAILURE'
      and lease_owner is null and lease_expires_at is null and last_error_class is not null
      and last_error_at is not null and completed_at is null
      and completed_ledger_integrity_hash is null)
  )
);

create index idx_decision_trace_outbox_pending
  on public.decision_trace_outbox (next_attempt_at, created_at)
  where processing_state = 'PENDING';
create index idx_decision_trace_outbox_owner_university
  on public.decision_trace_outbox (owner_user_id, university_id, created_at desc);

create or replace function public.validate_decision_trace_outbox_update()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  if new.event_id is distinct from old.event_id
    or new.revision_id is distinct from old.revision_id
    or new.owner_user_id is distinct from old.owner_user_id
    or new.university_id is distinct from old.university_id
    or new.major_id is distinct from old.major_id
    or new.study_plan_id is distinct from old.study_plan_id
    or new.study_plan_version is distinct from old.study_plan_version
    or new.target_period_id is distinct from old.target_period_id
    or new.revision is distinct from old.revision
    or new.event_type is distinct from old.event_type
    or new.snapshot_contract_version is distinct from old.snapshot_contract_version
    or new.source_snapshot is distinct from old.source_snapshot
    or new.created_at is distinct from old.created_at then
    raise exception 'Decision trace outbox event source is immutable'
      using errcode = '55000';
  end if;
  return new;
end;
$$;

create or replace function public.prevent_decision_trace_outbox_delete()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  raise exception 'Decision trace outbox events are durable and cannot be deleted'
    using errcode = '55000';
end;
$$;

create trigger validate_decision_trace_outbox_update_before_update
before update on public.decision_trace_outbox
for each row execute function public.validate_decision_trace_outbox_update();

create trigger prevent_decision_trace_outbox_delete_before_delete
before delete on public.decision_trace_outbox
for each row execute function public.prevent_decision_trace_outbox_delete();

-- Same signature and result contract as P6.4. The only additive behavior is the
-- required outbox insert for a newly INSERTED SUBMITTED revision.
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
  inserted_created_at timestamptz;
  course_count integer;
  course_index integer;
  snapshot_courses jsonb;
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
  if exists (select 1 from unnest(p_course_codes) code where code is null or btrim(code) = '')
    or cardinality(array(select distinct code from unnest(p_course_codes) code)) <> course_count
    or p_course_codes <> array(select code from unnest(p_course_codes) code order by code) then
    raise exception using errcode = '22023', message = 'Course codes must be unique canonical order';
  end if;
  if cardinality(array(select distinct course_id from unnest(p_course_ids) course_id)) <> course_count then
    raise exception using errcode = '22023', message = 'Course identifiers must be unique';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(concat_ws(
    chr(31), p_owner_user_id::text, p_university_id::text, p_major_id::text,
    p_study_plan_id::text, p_study_plan_version, p_target_period_id::text
  ), 0));
  next_revision := coalesce(p_expected_current_revision, 0) + 1;

  select revision.id, revision.intent_id, revision.content_fingerprint
  into existing_id, existing_intent_id, existing_fingerprint
  from public.mock_registration_intent_revisions revision
  where revision.owner_user_id = p_owner_user_id and revision.university_id = p_university_id
    and revision.major_id = p_major_id and revision.study_plan_id = p_study_plan_id
    and revision.study_plan_version = p_study_plan_version and revision.target_period_id = p_target_period_id
    and revision.revision = next_revision;
  if existing_id is not null then
    if existing_fingerprint = p_content_fingerprint then
      -- Pre-outbox history deliberately returns its legacy replay result without backfill.
      -- Post-outbox submitted revisions are constrained to at most one matching event.
      return query select 'IDEMPOTENT_REPLAY', existing_id, next_revision, existing_fingerprint;
    elsif existing_intent_id = p_intent_id then
      return query select 'PERSISTENCE_CONFLICT', existing_id, next_revision, existing_fingerprint;
    else
      return query select 'REVISION_CONFLICT', existing_id, next_revision, existing_fingerprint;
    end if;
    return;
  end if;

  select max(revision.revision) into current_revision
  from public.mock_registration_intent_revisions revision
  where revision.owner_user_id = p_owner_user_id and revision.university_id = p_university_id
    and revision.major_id = p_major_id and revision.study_plan_id = p_study_plan_id
    and revision.study_plan_version = p_study_plan_version and revision.target_period_id = p_target_period_id;
  if current_revision is distinct from p_expected_current_revision then
    return query select 'REVISION_CONFLICT', null::uuid, current_revision, null::text;
    return;
  end if;
  if exists (select 1 from public.mock_registration_target_periods period
             where period.id = p_target_period_id and period.is_expired) then
    raise exception using errcode = '23514', message = 'Mock Registration target period is expired';
  end if;

  insert into public.mock_registration_intent_revisions (
    intent_id, owner_user_id, university_id, major_id, study_plan_id, study_plan_version,
    target_period_id, revision, lifecycle_status, validation_status, content_fingerprint,
    intent_provenance, intent_source_version, validation_reason_codes, catalog_source_versions,
    prerequisite_source_versions, progress_state_version, progress_state_reference,
    phase5_policy_version, phase6_policy_version, p6_contract_version,
    target_period_source_version, transparency_notice_version, actor_class
  ) values (
    p_intent_id, p_owner_user_id, p_university_id, p_major_id, p_study_plan_id, p_study_plan_version,
    p_target_period_id, next_revision, p_lifecycle_status, p_validation_status, p_content_fingerprint,
    p_intent_provenance, p_intent_source_version, coalesce(p_validation_reason_codes, '{}'::text[]),
    coalesce(p_catalog_source_versions, '{}'::text[]), coalesce(p_prerequisite_source_versions, '{}'::text[]),
    p_progress_state_version, p_progress_state_reference, p_phase5_policy_version,
    p_phase6_policy_version, p_p6_contract_version, p_target_period_source_version,
    p_transparency_notice_version, p_actor_class
  ) returning id, created_at into inserted_id, inserted_created_at;

  for course_index in 1..course_count loop
    insert into public.mock_registration_intent_courses (
      revision_id, course_id, course_code, selection_order
    ) values (inserted_id, p_course_ids[course_index], p_course_codes[course_index], course_index);
  end loop;

  if p_lifecycle_status = 'SUBMITTED' then
    select coalesce(jsonb_agg(jsonb_build_object(
      'course_id', course.course_id, 'course_code', course.course_code,
      'selection_order', course.selection_order
    ) order by course.selection_order), '[]'::jsonb)
    into snapshot_courses
    from public.mock_registration_intent_courses course
    where course.revision_id = inserted_id;

    insert into public.decision_trace_outbox (
      event_id, revision_id, owner_user_id, university_id, major_id, study_plan_id,
      study_plan_version, target_period_id, revision, event_type, snapshot_contract_version,
      source_snapshot
    ) values (
      inserted_id, inserted_id, p_owner_user_id, p_university_id, p_major_id, p_study_plan_id,
      p_study_plan_version, p_target_period_id, next_revision, 'MOCK_REGISTRATION_SUBMIT', '1.0',
      jsonb_build_object(
        'revision_id', inserted_id, 'intent_id', p_intent_id,
        'owner_user_id', p_owner_user_id, 'university_id', p_university_id,
        'major_id', p_major_id, 'study_plan_id', p_study_plan_id,
        'study_plan_version', p_study_plan_version, 'target_period_id', p_target_period_id,
        'revision', next_revision, 'lifecycle_status', p_lifecycle_status,
        'validation_status', p_validation_status, 'content_fingerprint', p_content_fingerprint,
        'intent_provenance', p_intent_provenance, 'intent_source_version', p_intent_source_version,
        'validation_reason_codes', coalesce(p_validation_reason_codes, '{}'::text[]),
        'catalog_source_versions', coalesce(p_catalog_source_versions, '{}'::text[]),
        'prerequisite_source_versions', coalesce(p_prerequisite_source_versions, '{}'::text[]),
        'progress_state_version', p_progress_state_version,
        'progress_state_reference', p_progress_state_reference,
        'phase5_policy_version', p_phase5_policy_version,
        'phase6_policy_version', p_phase6_policy_version,
        'p6_contract_version', p_p6_contract_version,
        'target_period_source_version', p_target_period_source_version,
        'transparency_notice_version', p_transparency_notice_version,
        'actor_class', p_actor_class, 'created_at', inserted_created_at,
        'courses', snapshot_courses
      )
    );
  end if;

  return query select 'INSERTED', inserted_id, next_revision, p_content_fingerprint;
end;
$$;

alter table public.decision_trace_outbox enable row level security;
revoke all on table public.decision_trace_outbox from public, anon, authenticated, service_role;
revoke all on function public.validate_decision_trace_outbox_update() from public, anon, authenticated;
revoke all on function public.prevent_decision_trace_outbox_delete() from public, anon, authenticated;
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

comment on table public.decision_trace_outbox is
  'Local-only durable source-event outbox for newly persisted non-binding P6 Mock Registration submits. It is not a P8 ledger, enrollment, approval, or processor.';
comment on column public.decision_trace_outbox.source_snapshot is
  'Immutable versioned P6 transaction facts for a future trusted adapter; not a caller-supplied P8 ledger envelope and contains no P8 provenance/evidence mapping.';
