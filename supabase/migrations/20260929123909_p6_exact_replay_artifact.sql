-- Forward-only P6 submit replay material. Old revisions and ledger rows are untouched.
create table public.p6_submit_replay_artifacts (
  revision_id uuid primary key references public.mock_registration_intent_revisions(id) on delete restrict,
  university_id uuid not null,
  replay_contract_version text not null check (replay_contract_version = 'P6_REPLAY_ARTIFACT_V1'),
  engine_id text not null check (engine_id = 'P6_MOCK_REGISTRATION_VALIDATION'),
  engine_version text not null check (engine_version = '1.0'),
  canonical_payload text not null check (length(canonical_payload) between 2 and 1000000),
  canonical_sha256 text not null check (canonical_sha256 ~ '^[0-9a-f]{64}$'),
  source_versions text[] not null,
  created_at timestamptz not null default now()
);

alter table public.p6_submit_replay_artifacts enable row level security;
revoke all on public.p6_submit_replay_artifacts from public, anon, authenticated, service_role;
grant select on public.p6_submit_replay_artifacts to service_role;

create function public.reject_p6_replay_artifact_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception using errcode = '55000', message = 'P6 replay artifacts are immutable';
end;
$$;
create trigger p6_replay_artifact_immutable
before update or delete on public.p6_submit_replay_artifacts
for each row execute function public.reject_p6_replay_artifact_mutation();
revoke execute on function public.reject_p6_replay_artifact_mutation() from public, anon, authenticated;

-- One RPC transaction includes the accepted P6 revision/course/outbox function
-- and the private artifact. A failure in either part rolls back all four records.
create function public.persist_mock_registration_revision_with_replay(
  p_intent_id uuid, p_owner_user_id uuid, p_university_id uuid, p_major_id uuid,
  p_study_plan_id uuid, p_study_plan_version text, p_target_period_id uuid,
  p_expected_current_revision integer, p_lifecycle_status text, p_validation_status text,
  p_content_fingerprint text, p_intent_provenance text, p_intent_source_version text,
  p_validation_reason_codes text[], p_catalog_source_versions text[],
  p_prerequisite_source_versions text[], p_progress_state_version text,
  p_progress_state_reference text, p_phase5_policy_version text,
  p_phase6_policy_version text, p_p6_contract_version text,
  p_target_period_source_version text, p_transparency_notice_version text,
  p_actor_class text, p_course_ids uuid[], p_course_codes text[],
  p_replay_canonical_payload text, p_replay_canonical_sha256 text,
  p_replay_source_versions text[]
)
returns table (result_kind text, persisted_revision_id uuid,
               persisted_revision integer, persisted_fingerprint text)
language plpgsql security definer set search_path = '' as $$
declare
  v_result record;
  v_payload jsonb;
  v_artifact public.p6_submit_replay_artifacts%rowtype;
  v_revision public.mock_registration_intent_revisions%rowtype;
begin
  if p_lifecycle_status is distinct from 'SUBMITTED'
    or p_p6_contract_version is distinct from '1.0'
    or p_replay_canonical_payload is null
    or p_replay_canonical_sha256 is null
    or p_replay_canonical_sha256 is distinct from
      encode(pg_catalog.sha256(pg_catalog.convert_to(p_replay_canonical_payload, 'UTF8')), 'hex') then
    raise exception using errcode = '23514', message = 'Invalid P6 replay artifact';
  end if;
  v_payload := p_replay_canonical_payload::jsonb;
  if v_payload->>'contract' is distinct from 'P6_REPLAY_ARTIFACT_V1'
    or v_payload->>'engine_id' is distinct from 'P6_MOCK_REGISTRATION_VALIDATION'
    or v_payload->>'engine_version' is distinct from '1.0'
    or v_payload->'intent'->>'owner_scope_id' is distinct from p_owner_user_id::text
    or v_payload->'intent'->>'university_id' is distinct from p_university_id::text
    or v_payload->'intent'->>'study_plan_id' is distinct from p_study_plan_id::text
    or v_payload->'intent'->>'study_plan_version' is distinct from p_study_plan_version
    or v_payload->'historical_output'->>'status' is distinct from p_validation_status
    or v_payload->'historical_output'->>'content_fingerprint' is distinct from p_content_fingerprint
    or v_payload->'historical_output'->'reason_codes' is distinct from to_jsonb(p_validation_reason_codes)
    or v_payload->'historical_output'->'canonical_course_codes' is distinct from to_jsonb(p_course_codes)
    or v_payload->'context'->'source_versions' is distinct from to_jsonb(p_replay_source_versions) then
    raise exception using errcode = '23514', message = 'P6 replay artifact does not match submission';
  end if;

  select * into v_result from public.persist_mock_registration_revision(
    p_intent_id, p_owner_user_id, p_university_id, p_major_id, p_study_plan_id,
    p_study_plan_version, p_target_period_id, p_expected_current_revision,
    p_lifecycle_status, p_validation_status, p_content_fingerprint,
    p_intent_provenance, p_intent_source_version, p_validation_reason_codes,
    p_catalog_source_versions, p_prerequisite_source_versions,
    p_progress_state_version, p_progress_state_reference, p_phase5_policy_version,
    p_phase6_policy_version, p_p6_contract_version, p_target_period_source_version,
    p_transparency_notice_version, p_actor_class, p_course_ids, p_course_codes
  );
  if v_result.result_kind in ('INSERTED', 'IDEMPOTENT_REPLAY') then
    select * into v_revision from public.mock_registration_intent_revisions
    where id = v_result.persisted_revision_id;
    if not found or v_revision.university_id is distinct from p_university_id
      or v_revision.lifecycle_status is distinct from 'SUBMITTED'
      or not v_revision.outbox_required then
      raise exception using errcode = '23514', message = 'P6 replay revision identity mismatch';
    end if;
    if v_result.result_kind = 'INSERTED' then
      insert into public.p6_submit_replay_artifacts (
        revision_id, university_id, replay_contract_version, engine_id,
        engine_version, canonical_payload, canonical_sha256, source_versions
      ) values (
        v_revision.id, p_university_id, 'P6_REPLAY_ARTIFACT_V1',
        'P6_MOCK_REGISTRATION_VALIDATION', '1.0', p_replay_canonical_payload,
        p_replay_canonical_sha256, p_replay_source_versions
      );
    else
      select * into v_artifact from public.p6_submit_replay_artifacts
      where revision_id = v_revision.id;
      if not found or v_artifact.university_id is distinct from p_university_id
        or v_artifact.replay_contract_version is distinct from 'P6_REPLAY_ARTIFACT_V1'
        or v_artifact.engine_id is distinct from 'P6_MOCK_REGISTRATION_VALIDATION'
        or v_artifact.engine_version is distinct from '1.0'
        or v_artifact.canonical_payload is distinct from p_replay_canonical_payload
        or v_artifact.canonical_sha256 is distinct from p_replay_canonical_sha256
        or v_artifact.source_versions is distinct from p_replay_source_versions
        or v_artifact.canonical_sha256 is distinct from
          encode(pg_catalog.sha256(pg_catalog.convert_to(v_artifact.canonical_payload, 'UTF8')), 'hex') then
        raise exception using errcode = '23514', message = 'P6 replay artifact integrity mismatch';
      end if;
    end if;
  end if;
  return query select v_result.result_kind, v_result.persisted_revision_id,
                      v_result.persisted_revision, v_result.persisted_fingerprint;
end;
$$;
revoke execute on function public.persist_mock_registration_revision_with_replay(
  uuid, uuid, uuid, uuid, uuid, text, uuid, integer, text, text, text, text,
  text, text[], text[], text[], text, text, text, text, text, text, text,
  text, uuid[], text[], text, text, text[]
) from public, anon, authenticated;
grant execute on function public.persist_mock_registration_revision_with_replay(
  uuid, uuid, uuid, uuid, uuid, text, uuid, integer, text, text, text, text,
  text, text[], text[], text[], text, text, text, text, text, text, text,
  text, uuid[], text[], text, text, text[]
) to service_role;
