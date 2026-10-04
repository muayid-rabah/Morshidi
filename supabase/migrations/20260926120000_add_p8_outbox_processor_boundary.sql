-- P8 Slice 2C: Bounded, retry-safe decision-trace outbox processor boundary.
-- Minimal, service-only SECURITY DEFINER RPCs for bounded claiming, completing,
-- retry/releasing, and permanent-failing of P6 outbox events.
-- Source facts remain strictly immutable; direct table access remains revoked.

create or replace function public.claim_decision_trace_outbox_events(
  p_worker_id text,
  p_batch_size integer default 10,
  p_lease_seconds integer default 60,
  p_university_id uuid default null
)
returns table (
  event_id uuid,
  revision_id uuid,
  owner_user_id uuid,
  university_id uuid,
  major_id uuid,
  study_plan_id uuid,
  study_plan_version text,
  target_period_id uuid,
  revision integer,
  event_type text,
  snapshot_contract_version text,
  source_snapshot jsonb,
  attempt_count integer,
  lease_owner text,
  lease_expires_at timestamptz,
  outbox_required boolean,
  parent_revision_data jsonb
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_batch_size integer;
  v_lease_seconds integer;
begin
  if p_worker_id is null or btrim(p_worker_id) = '' then
    raise exception 'p_worker_id must be a nonblank string' using errcode = '22023';
  end if;

  v_batch_size := coalesce(p_batch_size, 10);
  if v_batch_size < 1 or v_batch_size > 100 then
    raise exception 'p_batch_size must be between 1 and 100' using errcode = '22023';
  end if;

  v_lease_seconds := coalesce(p_lease_seconds, 60);
  if v_lease_seconds < 10 or v_lease_seconds > 600 then
    raise exception 'p_lease_seconds must be between 10 and 600' using errcode = '22023';
  end if;

  return query
  with eligible as (
    select o.event_id as target_event_id
    from public.decision_trace_outbox o
    where (
      (o.processing_state = 'PENDING' and o.next_attempt_at <= now())
      or (o.processing_state = 'PROCESSING' and o.lease_expires_at < now())
    )
    and (p_university_id is null or o.university_id = p_university_id)
    order by o.next_attempt_at asc, o.created_at asc
    limit v_batch_size
    for update skip locked
  ),
  claimed as (
    update public.decision_trace_outbox o
    set processing_state = 'PROCESSING',
        lease_owner = p_worker_id || ':' || gen_random_uuid()::text,
        lease_expires_at = now() + (v_lease_seconds || ' seconds')::interval,
        processing_started_at = now(),
        attempt_count = o.attempt_count + 1,
        updated_at = now()
    from eligible
    where o.event_id = eligible.target_event_id
    returning o.*
  )
  select
    c.event_id,
    c.revision_id,
    c.owner_user_id,
    c.university_id,
    c.major_id,
    c.study_plan_id,
    c.study_plan_version,
    c.target_period_id,
    c.revision,
    c.event_type,
    c.snapshot_contract_version,
    c.source_snapshot,
    c.attempt_count,
    c.lease_owner,
    c.lease_expires_at,
    coalesce(r.outbox_required, false) as outbox_required,
    jsonb_build_object(
      'id', r.id,
      'intent_id', r.intent_id,
      'owner_user_id', r.owner_user_id,
      'university_id', r.university_id,
      'major_id', r.major_id,
      'study_plan_id', r.study_plan_id,
      'study_plan_version', r.study_plan_version,
      'target_period_id', r.target_period_id,
      'revision', r.revision,
      'lifecycle_status', r.lifecycle_status,
      'validation_status', r.validation_status,
      'content_fingerprint', r.content_fingerprint,
      'intent_provenance', r.intent_provenance,
      'intent_source_version', r.intent_source_version,
      'validation_reason_codes', r.validation_reason_codes,
      'catalog_source_versions', r.catalog_source_versions,
      'prerequisite_source_versions', r.prerequisite_source_versions,
      'progress_state_version', r.progress_state_version,
      'progress_state_reference', r.progress_state_reference,
      'phase5_policy_version', r.phase5_policy_version,
      'phase6_policy_version', r.phase6_policy_version,
      'p6_contract_version', r.p6_contract_version,
      'target_period_source_version', r.target_period_source_version,
      'transparency_notice_version', r.transparency_notice_version,
      'transparency_acknowledged_at', r.transparency_acknowledged_at,
      'actor_class', r.actor_class,
      'created_at', r.created_at,
      'outbox_required', r.outbox_required,
      'courses', coalesce(
        (
          select jsonb_agg(jsonb_build_object(
            'course_id', crs.course_id,
            'course_code', crs.course_code,
            'selection_order', crs.selection_order
          ) order by crs.selection_order)
          from public.mock_registration_intent_courses crs
          where crs.revision_id = r.id
        ),
        '[]'::jsonb
      )
    ) as parent_revision_data
  from claimed c
  left join public.mock_registration_intent_revisions r on r.id = c.revision_id;
end;
$$;

create or replace function public.complete_decision_trace_outbox_event(
  p_event_id uuid,
  p_claim_token text,
  p_completed_ledger_integrity_hash text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_updated integer;
begin
  if p_event_id is null then
    raise exception 'p_event_id must not be null' using errcode = '22023';
  end if;
  if p_claim_token is null or btrim(p_claim_token) = '' then
    raise exception 'p_claim_token must be a nonblank string' using errcode = '22023';
  end if;
  if p_completed_ledger_integrity_hash is null or p_completed_ledger_integrity_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'p_completed_ledger_integrity_hash must be a 64-char hex string' using errcode = '22023';
  end if;

  update public.decision_trace_outbox
  set processing_state = 'COMPLETED',
      lease_owner = null,
      lease_expires_at = null,
      completed_at = now(),
      completed_ledger_integrity_hash = p_completed_ledger_integrity_hash,
      updated_at = now()
  where event_id = p_event_id
    and lease_owner = p_claim_token
    and processing_state = 'PROCESSING';

  get diagnostics v_updated = row_count;
  if v_updated = 0 then
    raise exception 'Event % cannot be completed: stale claim token or invalid state', p_event_id
      using errcode = '55000';
  end if;

  return true;
end;
$$;

create or replace function public.release_decision_trace_outbox_event(
  p_event_id uuid,
  p_claim_token text,
  p_error_class text default 'TRANSIENT_P8_UNAVAILABLE',
  p_backoff_seconds integer default 30,
  p_max_attempts integer default 5
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_current_attempts integer;
  v_max_attempts integer;
  v_backoff_seconds integer;
begin
  if p_event_id is null then
    raise exception 'p_event_id must not be null' using errcode = '22023';
  end if;
  if p_claim_token is null or btrim(p_claim_token) = '' then
    raise exception 'p_claim_token must be a nonblank string' using errcode = '22023';
  end if;
  if p_error_class is not null and p_error_class not in (
    'TRANSIENT_P8_UNAVAILABLE', 'P8_DUPLICATE_MATCHED', 'P8_DUPLICATE_MISMATCH',
    'SOURCE_INTEGRITY_FAILURE', 'CONTRACT_FAILURE'
  ) then
    raise exception 'Invalid p_error_class: %', p_error_class using errcode = '22023';
  end if;

  v_max_attempts := coalesce(p_max_attempts, 5);
  v_backoff_seconds := coalesce(p_backoff_seconds, 30);
  if v_backoff_seconds < 1 or v_backoff_seconds > 86400 then
    raise exception 'p_backoff_seconds must be between 1 and 86400' using errcode = '22023';
  end if;

  select attempt_count into v_current_attempts
  from public.decision_trace_outbox
  where event_id = p_event_id
    and lease_owner = p_claim_token
    and processing_state = 'PROCESSING'
  for update;

  if not found then
    raise exception 'Event % cannot be released: stale claim token or invalid state', p_event_id
      using errcode = '55000';
  end if;

  if v_current_attempts >= v_max_attempts then
    update public.decision_trace_outbox
    set processing_state = 'PERMANENT_FAILURE',
        lease_owner = null,
        lease_expires_at = null,
        last_error_class = coalesce(p_error_class, 'CONTRACT_FAILURE'),
        last_error_at = now(),
        updated_at = now()
    where event_id = p_event_id;
  else
    update public.decision_trace_outbox
    set processing_state = 'PENDING',
        lease_owner = null,
        lease_expires_at = null,
        processing_started_at = null,
        next_attempt_at = now() + (v_backoff_seconds || ' seconds')::interval,
        last_error_class = p_error_class,
        last_error_at = now(),
        updated_at = now()
    where event_id = p_event_id;
  end if;

  return true;
end;
$$;

create or replace function public.fail_decision_trace_outbox_event(
  p_event_id uuid,
  p_claim_token text,
  p_error_class text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_updated integer;
begin
  if p_event_id is null then
    raise exception 'p_event_id must not be null' using errcode = '22023';
  end if;
  if p_claim_token is null or btrim(p_claim_token) = '' then
    raise exception 'p_claim_token must be a nonblank string' using errcode = '22023';
  end if;
  if p_error_class not in (
    'P8_DUPLICATE_MISMATCH', 'SOURCE_INTEGRITY_FAILURE', 'CONTRACT_FAILURE'
  ) then
    raise exception 'p_error_class for permanent failure must be P8_DUPLICATE_MISMATCH, SOURCE_INTEGRITY_FAILURE, or CONTRACT_FAILURE'
      using errcode = '22023';
  end if;

  update public.decision_trace_outbox
  set processing_state = 'PERMANENT_FAILURE',
      lease_owner = null,
      lease_expires_at = null,
      last_error_class = p_error_class,
      last_error_at = now(),
      updated_at = now()
  where event_id = p_event_id
    and lease_owner = p_claim_token
    and processing_state = 'PROCESSING';

  get diagnostics v_updated = row_count;
  if v_updated = 0 then
    raise exception 'Event % cannot be marked permanently failed: stale claim token or invalid state', p_event_id
      using errcode = '55000';
  end if;

  return true;
end;
$$;

revoke all on function public.claim_decision_trace_outbox_events(text, integer, integer, uuid)
  from public, anon, authenticated;
grant execute on function public.claim_decision_trace_outbox_events(text, integer, integer, uuid)
  to service_role;

revoke all on function public.complete_decision_trace_outbox_event(uuid, text, text)
  from public, anon, authenticated;
grant execute on function public.complete_decision_trace_outbox_event(uuid, text, text)
  to service_role;

revoke all on function public.release_decision_trace_outbox_event(uuid, text, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.release_decision_trace_outbox_event(uuid, text, text, integer, integer)
  to service_role;

revoke all on function public.fail_decision_trace_outbox_event(uuid, text, text)
  from public, anon, authenticated;
grant execute on function public.fail_decision_trace_outbox_event(uuid, text, text)
  to service_role;

comment on function public.claim_decision_trace_outbox_events is
  'P8 Slice 2C: Bounded atomic claim of pending P6 decision trace outbox events using FOR UPDATE SKIP LOCKED.';
comment on function public.complete_decision_trace_outbox_event is
  'P8 Slice 2C: Mark outbox event completed with verified ledger integrity hash; guarded by claim lease token.';
comment on function public.release_decision_trace_outbox_event is
  'P8 Slice 2C: Bounded retry/release of outbox event with backoff; transitions to PERMANENT_FAILURE on max attempts.';
comment on function public.fail_decision_trace_outbox_event is
  'P8 Slice 2C: Fail-closed permanent transition for unrecoverable outbox mapper or integrity failures.';
