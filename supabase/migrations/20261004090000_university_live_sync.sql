create table if not exists public.university_event_inbox (
  event_id uuid primary key,
  idempotency_key text not null unique,
  event_type text not null,
  event_version bigint not null check (event_version > 0),
  occurred_at timestamptz not null,
  student_id text,
  payload jsonb not null,
  received_at timestamptz not null default now()
);

create table if not exists public.university_event_versions (
  aggregate_key text primary key,
  last_version bigint not null check (last_version > 0),
  occurred_at timestamptz not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.student_notifications (
  id bigint generated always as identity primary key,
  event_id uuid not null references public.university_event_inbox(event_id) on delete cascade,
  student_id text,
  summary text not null,
  created_at timestamptz not null default now(),
  unique (event_id, student_id)
);

create index if not exists student_notifications_scope_created_idx
  on public.student_notifications (student_id, created_at desc, id desc);
create index if not exists university_event_inbox_occurred_idx
  on public.university_event_inbox (occurred_at desc, event_id);

alter table public.university_event_inbox enable row level security;
alter table public.university_event_inbox force row level security;
alter table public.university_event_versions enable row level security;
alter table public.university_event_versions force row level security;
alter table public.student_notifications enable row level security;
alter table public.student_notifications force row level security;

revoke all on public.university_event_inbox, public.university_event_versions,
  public.student_notifications from public, anon, authenticated;
grant select, insert on public.university_event_inbox to service_role;
grant select, insert, update on public.university_event_versions to service_role;
grant select, insert on public.student_notifications to service_role;
grant usage, select on sequence public.student_notifications_id_seq to service_role;

create or replace function public.ingest_university_event(p_event jsonb)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_id uuid := (p_event ->> 'id')::uuid;
  v_key text := p_event ->> 'idempotencyKey';
  v_type text := p_event ->> 'type';
  v_version bigint := (p_event ->> 'version')::bigint;
  v_occurred timestamptz := (p_event ->> 'occurredAt')::timestamptz;
  v_student text := nullif(p_event ->> 'studentId', '');
  v_payload jsonb := coalesce(p_event -> 'payload', '{}'::jsonb);
  v_aggregate text;
  v_previous bigint;
  v_inserted integer;
  v_summary text;
begin
  if v_id is null or v_key is null or btrim(v_key) = '' or v_type is null
     or v_version is null or v_version < 1 or v_occurred is null
     or jsonb_typeof(v_payload) <> 'object' then
    raise exception 'invalid university event' using errcode = '22023';
  end if;

  insert into public.university_event_inbox(event_id,idempotency_key,event_type,event_version,
    occurred_at,student_id,payload)
  values (v_id,v_key,v_type,v_version,v_occurred,v_student,v_payload)
  on conflict do nothing;
  get diagnostics v_inserted = row_count;
  if v_inserted = 0 then
    return jsonb_build_object('duplicate', true, 'applied', false);
  end if;

  v_aggregate := case
    when v_student is not null then 'student:' || v_student
    when v_type like 'registration.%' then 'calendar'
    else 'offering:' || coalesce(v_payload ->> 'sectionId', v_type)
  end;
  perform pg_advisory_xact_lock(hashtextextended(v_aggregate, 0));
  select last_version into v_previous from public.university_event_versions
    where aggregate_key = v_aggregate for update;
  if v_previous is not null and v_version <= v_previous then
    return jsonb_build_object('duplicate', false, 'applied', false, 'stale', true);
  end if;
  insert into public.university_event_versions(aggregate_key,last_version,occurred_at)
  values (v_aggregate,v_version,v_occurred)
  on conflict (aggregate_key) do update set last_version = excluded.last_version,
    occurred_at = excluded.occurred_at, updated_at = now();

  v_summary := case v_type
    when 'grade.posted' then 'نزلت علامة مادة ' || coalesce(v_payload ->> 'courseName', v_payload ->> 'courseCode', '')
    when 'registration.opened' then 'فُتح التسجيل للفصل الحالي'
    when 'registration.closed' then 'أُغلق التسجيل للفصل الحالي'
    when 'section.opened' then 'انفتحت شعبة للمادة ' || coalesce(v_payload ->> 'courseCode', '')
    when 'section.closed' then 'أُغلقت شعبة للمادة ' || coalesce(v_payload ->> 'courseCode', '')
    when 'offering.updated' then 'تحدّثت شعبة المادة ' || coalesce(v_payload ->> 'courseCode', '')
    when 'schedule.changed' then 'تحدّث جدولك الدراسي'
    when 'plan.updated' then 'تحدّثت خطتك الدراسية'
    when 'record.updated' then 'تحدّث سجلك الأكاديمي'
    else 'وصل تحديث من الجامعة'
  end;
  insert into public.student_notifications(event_id,student_id,summary)
    values (v_id,v_student,v_summary);
  return jsonb_build_object('duplicate', false, 'applied', true);
end;
$$;

revoke all on function public.ingest_university_event(jsonb) from public, anon, authenticated;
grant execute on function public.ingest_university_event(jsonb) to service_role;
