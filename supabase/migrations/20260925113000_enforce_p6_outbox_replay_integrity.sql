-- Forward-only correction for the P6 transactional outbox.
-- `false` means only that this row has no explicit requirement marker; it does
-- not prove when it was created or that an outbox event was historically valid.

alter table public.mock_registration_intent_revisions
  add column outbox_required boolean not null default false;

comment on column public.mock_registration_intent_revisions.outbox_required is
  'Forward-only P6 outbox requirement marker. false is LEGACY/UNVERIFIED, not evidence of pre-outbox provenance. The trusted P6 persistence RPC alone sets true for new SUBMITTED revisions.';

-- Keep the P6.4 signature and response schema.  The only corrective behavior is
-- (1) setting the immutable forward-only marker on new SUBMITTED rows and
-- (2) checking a required event against immutable P6 facts before replaying it.
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
  existing_record public.mock_registration_intent_revisions%rowtype;
  existing_event public.decision_trace_outbox%rowtype;
  inserted_id uuid;
  inserted_created_at timestamptz;
  course_count integer;
  course_index integer;
  snapshot_courses jsonb;
  expected_snapshot jsonb;
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

  select revision.*
  into existing_record
  from public.mock_registration_intent_revisions revision
  where revision.owner_user_id = p_owner_user_id and revision.university_id = p_university_id
    and revision.major_id = p_major_id and revision.study_plan_id = p_study_plan_id
    and revision.study_plan_version = p_study_plan_version and revision.target_period_id = p_target_period_id
    and revision.revision = next_revision;
  if found then
    if existing_record.content_fingerprint = p_content_fingerprint then
      if existing_record.outbox_required then
        select event.*
        into existing_event
        from public.decision_trace_outbox event
        where event.revision_id = existing_record.id;
        if not found then
          raise exception using errcode = '23514',
            message = 'Required P6 outbox event is missing for replay';
        end if;

        select coalesce(jsonb_agg(jsonb_build_object(
          'course_id', course.course_id, 'course_code', course.course_code,
          'selection_order', course.selection_order
        ) order by course.selection_order), '[]'::jsonb)
        into snapshot_courses
        from public.mock_registration_intent_courses course
        where course.revision_id = existing_record.id;

        expected_snapshot := jsonb_build_object(
          'revision_id', existing_record.id, 'intent_id', existing_record.intent_id,
          'owner_user_id', existing_record.owner_user_id, 'university_id', existing_record.university_id,
          'major_id', existing_record.major_id, 'study_plan_id', existing_record.study_plan_id,
          'study_plan_version', existing_record.study_plan_version, 'target_period_id', existing_record.target_period_id,
          'revision', existing_record.revision, 'lifecycle_status', existing_record.lifecycle_status,
          'validation_status', existing_record.validation_status, 'content_fingerprint', existing_record.content_fingerprint,
          'intent_provenance', existing_record.intent_provenance, 'intent_source_version', existing_record.intent_source_version,
          'validation_reason_codes', existing_record.validation_reason_codes,
          'catalog_source_versions', existing_record.catalog_source_versions,
          'prerequisite_source_versions', existing_record.prerequisite_source_versions,
          'progress_state_version', existing_record.progress_state_version,
          'progress_state_reference', existing_record.progress_state_reference,
          'phase5_policy_version', existing_record.phase5_policy_version,
          'phase6_policy_version', existing_record.phase6_policy_version,
          'p6_contract_version', existing_record.p6_contract_version,
          'target_period_source_version', existing_record.target_period_source_version,
          'transparency_notice_version', existing_record.transparency_notice_version,
          'actor_class', existing_record.actor_class, 'created_at', existing_record.created_at,
          'courses', snapshot_courses
        );

        if existing_event.event_id is distinct from existing_record.id
          or existing_event.revision_id is distinct from existing_record.id
          or existing_event.owner_user_id is distinct from existing_record.owner_user_id
          or existing_event.university_id is distinct from existing_record.university_id
          or existing_event.major_id is distinct from existing_record.major_id
          or existing_event.study_plan_id is distinct from existing_record.study_plan_id
          or existing_event.study_plan_version is distinct from existing_record.study_plan_version
          or existing_event.target_period_id is distinct from existing_record.target_period_id
          or existing_event.revision is distinct from existing_record.revision
          or existing_event.event_type is distinct from 'MOCK_REGISTRATION_SUBMIT'
          or existing_event.snapshot_contract_version is distinct from '1.0'
          or existing_event.source_snapshot is distinct from expected_snapshot then
          raise exception using errcode = '23514',
            message = 'Required P6 outbox event integrity mismatch during replay';
        end if;
      end if;
      return query select 'IDEMPOTENT_REPLAY', existing_record.id, next_revision, existing_record.content_fingerprint;
    elsif existing_record.intent_id = p_intent_id then
      return query select 'PERSISTENCE_CONFLICT', existing_record.id, next_revision, existing_record.content_fingerprint;
    else
      return query select 'REVISION_CONFLICT', existing_record.id, next_revision, existing_record.content_fingerprint;
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
    target_period_source_version, transparency_notice_version, actor_class, outbox_required
  ) values (
    p_intent_id, p_owner_user_id, p_university_id, p_major_id, p_study_plan_id, p_study_plan_version,
    p_target_period_id, next_revision, p_lifecycle_status, p_validation_status, p_content_fingerprint,
    p_intent_provenance, p_intent_source_version, coalesce(p_validation_reason_codes, '{}'::text[]),
    coalesce(p_catalog_source_versions, '{}'::text[]), coalesce(p_prerequisite_source_versions, '{}'::text[]),
    p_progress_state_version, p_progress_state_reference, p_phase5_policy_version,
    p_phase6_policy_version, p_p6_contract_version, p_target_period_source_version,
    p_transparency_notice_version, p_actor_class, p_lifecycle_status = 'SUBMITTED'
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

-- Reassert the function boundary after CREATE OR REPLACE; no public overload or
-- direct table authority is introduced by this corrective migration.
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
