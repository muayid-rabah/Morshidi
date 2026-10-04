-- P8 Runtime Slice 2A: local Decision Trace Ledger persistence foundation.
-- This migration stores only validated material decision records and typed references.
-- It intentionally does not implement a Python repository, user-facing retrieval, replay,
-- retention/erasure, RAG, graph, impact, or institutional query capabilities.

create table public.decision_trace_ledger (
  ledger_entry_id text primary key,
  decision_type text not null,
  materiality_class text not null,
  actor_class text not null,
  actor_id text,
  subject_scope_type text not null,
  subject_scope_id text not null,
  university_id uuid not null references public.universities(id) on delete restrict,
  student_user_id uuid references auth.users(id) on delete restrict,
  source_engine text not null,
  source_engine_version text not null,
  policy_version text not null,
  source_versions text[] not null,
  input_state_reference text,
  scenario_id text,
  decision_status text not null,
  outcome_reference text not null,
  domain_trace_reference text,
  provenance_class text not null,
  created_at timestamptz not null,
  redaction_profile text not null,
  integrity_hash text not null,
  previous_entry_hash text,
  supersedes_entry_id text references public.decision_trace_ledger(ledger_entry_id) on delete restrict,
  replay_status text not null,
  limitations text[] not null default '{}'::text[],
  hash_contract_version text not null,
  decision_schema_version text not null,

  constraint decision_trace_ledger_identity_nonblank
    check (btrim(ledger_entry_id) <> ''),
  constraint decision_trace_ledger_scope_nonblank
    check (btrim(subject_scope_id) <> ''),
  constraint decision_trace_ledger_engine_nonblank
    check (btrim(source_engine) <> '' and btrim(source_engine_version) <> ''),
  constraint decision_trace_ledger_policy_and_outcome_nonblank
    check (btrim(policy_version) <> '' and btrim(outcome_reference) <> ''),
  constraint decision_trace_ledger_source_versions_nonempty
    check (cardinality(source_versions) > 0 and array_position(source_versions, null::text) is null),
  constraint decision_trace_ledger_limitations_no_nulls
    check (array_position(limitations, null::text) is null),
  constraint decision_trace_ledger_hash_shape
    check (integrity_hash ~ '^[0-9a-f]{64}$'),
  constraint decision_trace_ledger_previous_hash_shape
    check (previous_entry_hash is null or previous_entry_hash ~ '^[0-9a-f]{64}$'),
  constraint decision_trace_ledger_hash_contract
    check (hash_contract_version = '1.0'),
  constraint decision_trace_ledger_schema_contract
    check (decision_schema_version = '1.0'),
  constraint decision_trace_ledger_actor_class
    check (actor_class in (
      'STUDENT', 'ACADEMIC_ADVISOR', 'INSTITUTIONAL_ANALYST',
      'AUTHORIZED_AUDITOR', 'SYSTEM_SCHEDULER', 'SYSTEM_ENGINE'
    )),
  constraint decision_trace_ledger_subject_scope
    check (subject_scope_type in (
      'STUDENT_INDIVIDUAL', 'INSTITUTIONAL_PERIOD', 'CURRICULAR_PROGRAM', 'POLICY_DOCUMENT'
    )),
  constraint decision_trace_ledger_student_scope
    check (
      (subject_scope_type = 'STUDENT_INDIVIDUAL' and student_user_id is not null)
      or (subject_scope_type <> 'STUDENT_INDIVIDUAL' and student_user_id is null)
    ),
  constraint decision_trace_ledger_decision_status
    check (decision_status in (
      'EXECUTED', 'VALIDATED', 'REVALIDATED_VALID', 'REVALIDATED_INVALID',
      'ABSTAINED', 'FLAGGED_REVIEW', 'SUPERSEDED'
    )),
  constraint decision_trace_ledger_provenance_class
    check (provenance_class in (
      'AUTHORITATIVE_TRANSACTION', 'VERIFIED_REVALIDATION',
      'PERIOD_SNAPSHOT', 'GOVERNED_ASSESSMENT'
    )),
  constraint decision_trace_ledger_authoritative_scenario
    check (provenance_class <> 'AUTHORITATIVE_TRANSACTION' or scenario_id is null),
  constraint decision_trace_ledger_redaction_profile
    check (redaction_profile in (
      'STUDENT_SAFE', 'ADVISOR_SAFE', 'AGGREGATE_ANALYST', 'FULL_AUDIT', 'PUBLIC_REDACTED'
    )),
  constraint decision_trace_ledger_replay_status
    check (replay_status in ('REPLAYABLE_EXACT', 'REPLAYABLE_CURRENT_ONLY', 'NOT_REPLAYABLE')),
  constraint decision_trace_ledger_supersession_pair
    check (
      (supersedes_entry_id is null and previous_entry_hash is null)
      or (supersedes_entry_id is not null and previous_entry_hash is not null)
    ),
  constraint decision_trace_ledger_no_self_supersession
    check (supersedes_entry_id is null or supersedes_entry_id <> ledger_entry_id),
  constraint decision_trace_ledger_material_event_registry
    check (
      (decision_type = 'MOCK_REGISTRATION_SUBMIT' and materiality_class = 'LEDGER_REQUIRED')
      or (decision_type = 'MOCK_REGISTRATION_WITHDRAW' and materiality_class = 'LEDGER_REQUIRED')
      or (decision_type = 'MOCK_REGISTRATION_REVALIDATE' and materiality_class = 'LEDGER_REQUIRED')
      or (decision_type = 'ADVISOR_FORMAL_GUIDANCE' and materiality_class = 'LEDGER_REQUIRED')
      or (decision_type = 'INSTITUTIONAL_PERIOD_DEMAND_SNAPSHOT' and materiality_class = 'LEDGER_REQUIRED')
      or (decision_type = 'INSTITUTIONAL_BOTTLENECK_SNAPSHOT' and materiality_class = 'LEDGER_REQUIRED')
      or (decision_type = 'INSTITUTIONAL_ALERT_TRIGGERED' and materiality_class = 'LEDGER_REQUIRED')
      or (decision_type = 'CHANGE_IMPACT_EVALUATION' and materiality_class = 'LEDGER_REQUIRED')
      or (decision_type = 'FORMAL_POLICY_CONSULTATION' and materiality_class = 'LEDGER_OPTIONAL')
    )
);

create table public.decision_trace_evidence (
  ledger_entry_id text not null references public.decision_trace_ledger(ledger_entry_id) on delete restrict,
  evidence_position integer not null,
  source text not null,
  identifier text not null,
  version text not null,
  locator text,
  uri text,
  primary key (ledger_entry_id, evidence_position),
  constraint decision_trace_evidence_position_positive check (evidence_position > 0),
  constraint decision_trace_evidence_required_nonblank
    check (btrim(source) <> '' and btrim(identifier) <> '' and btrim(version) <> ''),
  constraint decision_trace_evidence_locator_nonblank_when_present
    check (locator is null or btrim(locator) <> ''),
  constraint decision_trace_evidence_uri_nonblank_when_present
    check (uri is null or btrim(uri) <> ''),
  unique nulls not distinct (ledger_entry_id, source, identifier, version, locator, uri)
);

create index idx_decision_trace_ledger_university_created_at
  on public.decision_trace_ledger (university_id, created_at desc);
create index idx_decision_trace_ledger_student_created_at
  on public.decision_trace_ledger (student_user_id, created_at desc)
  where student_user_id is not null;
create unique index idx_decision_trace_ledger_one_successor
  on public.decision_trace_ledger (supersedes_entry_id)
  where supersedes_entry_id is not null;
create index idx_decision_trace_evidence_parent_position
  on public.decision_trace_evidence (ledger_entry_id, evidence_position);

create or replace function public.validate_decision_trace_supersession()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare
  predecessor public.decision_trace_ledger%rowtype;
begin
  if new.supersedes_entry_id is null then
    return new;
  end if;

  select * into predecessor
  from public.decision_trace_ledger
  where ledger_entry_id = new.supersedes_entry_id;

  if not found then
    raise exception 'Decision trace predecessor does not exist'
      using errcode = '23503';
  end if;

  if new.previous_entry_hash is distinct from predecessor.integrity_hash then
    raise exception 'Decision trace previous_entry_hash does not match predecessor'
      using errcode = '23514';
  end if;

  if new.university_id is distinct from predecessor.university_id
    or new.subject_scope_type is distinct from predecessor.subject_scope_type
    or new.subject_scope_id is distinct from predecessor.subject_scope_id
    or new.student_user_id is distinct from predecessor.student_user_id then
    raise exception 'Decision trace supersession scope does not match predecessor'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create or replace function public.prevent_decision_trace_history_mutation()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  raise exception 'Decision trace history is append-only; use a new superseding entry'
    using errcode = '55000';
end;
$$;

create trigger validate_decision_trace_supersession_before_insert
before insert on public.decision_trace_ledger
for each row execute function public.validate_decision_trace_supersession();

create trigger prevent_decision_trace_ledger_mutation
before update or delete on public.decision_trace_ledger
for each row execute function public.prevent_decision_trace_history_mutation();

create trigger prevent_decision_trace_evidence_mutation
before update or delete on public.decision_trace_evidence
for each row execute function public.prevent_decision_trace_history_mutation();

create or replace function public.append_decision_trace_ledger(
  p_entry jsonb,
  p_evidence jsonb default '[]'::jsonb
)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  expected_entry_keys constant text[] := array[
    'ledger_entry_id', 'decision_type', 'materiality_class', 'actor_class', 'actor_id',
    'subject_scope_type', 'subject_scope_id', 'university_id', 'student_user_id',
    'source_engine', 'source_engine_version', 'policy_version', 'source_versions',
    'input_state_reference', 'scenario_id', 'decision_status', 'outcome_reference',
    'domain_trace_reference', 'provenance_class', 'created_at', 'redaction_profile',
    'integrity_hash', 'previous_entry_hash', 'supersedes_entry_id', 'replay_status',
    'limitations', 'hash_contract_version', 'decision_schema_version'
  ];
  expected_evidence_keys constant text[] := array['source', 'identifier', 'version', 'locator', 'uri'];
  supplied_key text;
  evidence_item jsonb;
  evidence_ordinality bigint;
  source_version_values text[];
  limitation_values text[];
  sorted_values text[];
  total_values bigint;
  distinct_values bigint;
  appended_ledger_entry_id text;
begin
  if jsonb_typeof(p_entry) is distinct from 'object' then
    raise exception 'p_entry must be a JSON object' using errcode = '22023';
  end if;
  if not (p_entry ?& expected_entry_keys) then
    raise exception 'p_entry is missing required canonical ledger fields' using errcode = '22023';
  end if;
  if exists (
    select 1
    from jsonb_object_keys(p_entry) as supplied(supplied_key)
    where not (supplied.supplied_key = any(expected_entry_keys))
  ) then
    raise exception 'p_entry contains an unsupported field' using errcode = '22023';
  end if;
  if jsonb_typeof(p_entry -> 'source_versions') is distinct from 'array'
    or jsonb_array_length(p_entry -> 'source_versions') = 0 then
    raise exception 'source_versions must be a non-empty JSON array' using errcode = '22023';
  end if;
  if jsonb_typeof(p_entry -> 'limitations') is distinct from 'array' then
    raise exception 'limitations must be a JSON array' using errcode = '22023';
  end if;
  if jsonb_typeof(p_evidence) is distinct from 'array' then
    raise exception 'p_evidence must be a JSON array' using errcode = '22023';
  end if;
  if (p_entry ->> 'created_at') !~ 'Z$' then
    raise exception 'created_at must use canonical UTC Z notation' using errcode = '22023';
  end if;

  select array_agg(value), count(*), count(distinct value)
  into source_version_values, total_values, distinct_values
  from jsonb_array_elements_text(p_entry -> 'source_versions') as values(value);
  select array_agg(value order by value)
  into sorted_values
  from unnest(source_version_values) as values(value);
  if source_version_values is distinct from sorted_values
    or total_values <> distinct_values
    or exists (select 1 from unnest(source_version_values) as values(value) where btrim(value) = '') then
    raise exception 'source_versions must be nonblank, unique, and canonical-sorted' using errcode = '22023';
  end if;

  select coalesce(array_agg(value), '{}'::text[]), count(*), count(distinct value)
  into limitation_values, total_values, distinct_values
  from jsonb_array_elements_text(p_entry -> 'limitations') as values(value);
  select coalesce(array_agg(value order by value), '{}'::text[])
  into sorted_values
  from unnest(limitation_values) as values(value);
  if limitation_values is distinct from sorted_values
    or total_values <> distinct_values
    or exists (select 1 from unnest(limitation_values) as values(value) where btrim(value) = '') then
    raise exception 'limitations must be nonblank, unique, and canonical-sorted' using errcode = '22023';
  end if;

  insert into public.decision_trace_ledger (
    ledger_entry_id, decision_type, materiality_class, actor_class, actor_id,
    subject_scope_type, subject_scope_id, university_id, student_user_id,
    source_engine, source_engine_version, policy_version, source_versions,
    input_state_reference, scenario_id, decision_status, outcome_reference,
    domain_trace_reference, provenance_class, created_at, redaction_profile,
    integrity_hash, previous_entry_hash, supersedes_entry_id, replay_status,
    limitations, hash_contract_version, decision_schema_version
  ) values (
    p_entry ->> 'ledger_entry_id', p_entry ->> 'decision_type', p_entry ->> 'materiality_class',
    p_entry ->> 'actor_class', nullif(btrim(p_entry ->> 'actor_id'), ''),
    p_entry ->> 'subject_scope_type', p_entry ->> 'subject_scope_id',
    (p_entry ->> 'university_id')::uuid,
    nullif(btrim(p_entry ->> 'student_user_id'), '')::uuid,
    p_entry ->> 'source_engine', p_entry ->> 'source_engine_version', p_entry ->> 'policy_version',
    source_version_values,
    nullif(btrim(p_entry ->> 'input_state_reference'), ''), nullif(btrim(p_entry ->> 'scenario_id'), ''),
    p_entry ->> 'decision_status', p_entry ->> 'outcome_reference',
    nullif(btrim(p_entry ->> 'domain_trace_reference'), ''), p_entry ->> 'provenance_class',
    (p_entry ->> 'created_at')::timestamptz, p_entry ->> 'redaction_profile',
    p_entry ->> 'integrity_hash', nullif(btrim(p_entry ->> 'previous_entry_hash'), ''),
    nullif(btrim(p_entry ->> 'supersedes_entry_id'), ''), p_entry ->> 'replay_status',
    limitation_values, p_entry ->> 'hash_contract_version', p_entry ->> 'decision_schema_version'
  ) returning ledger_entry_id into appended_ledger_entry_id;

  for evidence_item, evidence_ordinality in
    select value, ordinality
    from jsonb_array_elements(p_evidence) with ordinality as evidence(value, ordinality)
  loop
    if jsonb_typeof(evidence_item) is distinct from 'object'
      or not (evidence_item ?& array['source', 'identifier', 'version']) then
      raise exception 'evidence item is missing required reference fields' using errcode = '22023';
    end if;
    if exists (
      select 1
      from jsonb_object_keys(evidence_item) as supplied(supplied_key)
      where not (supplied.supplied_key = any(expected_evidence_keys))
    ) then
      raise exception 'evidence item contains an unsupported field' using errcode = '22023';
    end if;
    if coalesce(btrim(evidence_item ->> 'source'), '') = ''
      or coalesce(btrim(evidence_item ->> 'identifier'), '') = ''
      or coalesce(btrim(evidence_item ->> 'version'), '') = '' then
      raise exception 'evidence source, identifier, and version must be nonblank' using errcode = '22023';
    end if;

    insert into public.decision_trace_evidence (
      ledger_entry_id, evidence_position, source, identifier, version, locator, uri
    ) values (
      appended_ledger_entry_id, evidence_ordinality::integer,
      btrim(evidence_item ->> 'source'), btrim(evidence_item ->> 'identifier'), btrim(evidence_item ->> 'version'),
      nullif(btrim(evidence_item ->> 'locator'), ''), nullif(btrim(evidence_item ->> 'uri'), '')
    );
  end loop;

  return appended_ledger_entry_id;
end;
$$;

alter table public.decision_trace_ledger enable row level security;
alter table public.decision_trace_evidence enable row level security;

revoke all on table public.decision_trace_ledger from public, anon, authenticated, service_role;
revoke all on table public.decision_trace_evidence from public, anon, authenticated, service_role;

-- The server credential is not a user authorization mechanism. It receives no direct write grant;
-- writes must use the narrow SECURITY DEFINER append RPC. Read authorization is deferred to Slice 2B.
grant select on table public.decision_trace_ledger to service_role;
grant select on table public.decision_trace_evidence to service_role;

revoke all on function public.append_decision_trace_ledger(jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.append_decision_trace_ledger(jsonb, jsonb) to service_role;

revoke all on function public.validate_decision_trace_supersession() from public, anon, authenticated;
revoke all on function public.prevent_decision_trace_history_mutation() from public, anon, authenticated;

comment on table public.decision_trace_ledger is
  'P8 Slice 2A immutable, material-decision persistence. SHA-256 is an integrity value, not authorization or a signature.';
comment on table public.decision_trace_evidence is
  'P8 Slice 2A typed evidence references owned by an immutable decision trace parent; raw policy content is not stored.';
comment on function public.append_decision_trace_ledger(jsonb, jsonb) is
  'P8 Slice 2A service-role-only atomic append. Slice 2B server code must authorize scope and verify the existing Slice 1 hash before calling it.';
