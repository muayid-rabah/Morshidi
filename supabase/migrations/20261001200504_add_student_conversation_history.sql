-- P15.6: durable, owner/tenant-scoped student advisor conversations.
-- The application writes with its server credential; authenticated clients may
-- read only their own current-institution rows. No automatic retention expiry.
create table public.student_conversation_threads (
  id uuid primary key default gen_random_uuid(),
  -- Profile deletion must not silently erase chat outside governed privacy review.
  profile_id uuid not null references public.student_academic_profiles(id) on delete restrict,
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  institution_id uuid not null references public.universities(id) on delete restrict,
  title text not null default 'New conversation' check (length(title) between 1 and 120),
  status text not null default 'ACTIVE' check (status in ('ACTIVE', 'ARCHIVED')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_message_at timestamptz,
  summary_text text check (summary_text is null or length(summary_text) <= 800),
  summary_version text not null default 'P15_6_BOUNDED_PREFERENCES_V1',
  unique (id, owner_user_id, institution_id)
);

create table public.student_conversation_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null,
  owner_user_id uuid not null,
  institution_id uuid not null,
  role text not null check (role in ('USER', 'ASSISTANT')),
  content text not null check (length(content) between 1 and 8000),
  message_type text not null default 'TEXT' check (message_type in ('TEXT', 'ACADEMIC_EXPLANATION')),
  provenance text not null check (provenance in ('USER_STATED', 'DETERMINISTIC_EXPLANATION', 'GUARDED_PROVIDER')),
  created_at timestamptz not null default now(),
  foreign key (thread_id, owner_user_id, institution_id)
    references public.student_conversation_threads(id, owner_user_id, institution_id) on delete cascade
);

create table public.student_conversation_preferences (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  institution_id uuid not null references public.universities(id) on delete restrict,
  preference_key text not null check (preference_key in ('regular_load', 'summer_enabled', 'summer_load', 'graduation_pace')),
  preference_value text not null check (length(preference_value) between 1 and 32),
  provenance text not null check (provenance = 'USER_STATED'),
  source_message_id uuid references public.student_conversation_messages(id) on delete set null,
  created_at timestamptz not null default now()
);

create index student_conversation_threads_owner_idx on public.student_conversation_threads
  (owner_user_id, institution_id, updated_at desc);
create index student_conversation_messages_thread_idx on public.student_conversation_messages
  (thread_id, owner_user_id, institution_id, created_at, id);
create index student_conversation_preferences_owner_idx on public.student_conversation_preferences
  (owner_user_id, institution_id, preference_key, created_at desc);

create function public.validate_student_conversation_scope()
returns trigger language plpgsql set search_path = '' as $$
begin
  if not exists (
    select 1 from public.student_academic_profiles p
    join public.study_plans sp on sp.id = p.study_plan_id
    join public.majors m on m.id = sp.major_id
    join public.faculties f on f.id = m.faculty_id
    where p.id = new.profile_id and p.owner_user_id = new.owner_user_id
      and f.university_id = new.institution_id
  ) then
    raise exception 'Conversation owner/institution scope mismatch' using errcode = '23514';
  end if;
  return new;
end;
$$;
create trigger student_conversation_scope_guard
before insert or update on public.student_conversation_threads
for each row execute function public.validate_student_conversation_scope();

create function public.validate_student_conversation_preference_scope()
returns trigger language plpgsql set search_path = '' as $$
begin
  if not exists (
    select 1 from public.student_academic_profiles p
    join public.study_plans sp on sp.id = p.study_plan_id
    join public.majors m on m.id = sp.major_id
    join public.faculties f on f.id = m.faculty_id
    where p.owner_user_id = new.owner_user_id and f.university_id = new.institution_id
  ) or (new.source_message_id is not null and not exists (
    select 1 from public.student_conversation_messages msg
    where msg.id = new.source_message_id and msg.owner_user_id = new.owner_user_id
      and msg.institution_id = new.institution_id and msg.role = 'USER'
  )) then
    raise exception 'Conversation preference scope mismatch' using errcode = '23514';
  end if;
  return new;
end;
$$;
create trigger student_conversation_preference_scope_guard
before insert or update on public.student_conversation_preferences
for each row execute function public.validate_student_conversation_preference_scope();

alter table public.student_conversation_threads enable row level security;
alter table public.student_conversation_messages enable row level security;
alter table public.student_conversation_preferences enable row level security;
revoke all on public.student_conversation_threads, public.student_conversation_messages,
  public.student_conversation_preferences from anon, authenticated;
grant select on public.student_conversation_threads, public.student_conversation_messages,
  public.student_conversation_preferences to authenticated;
grant select, insert, update, delete on public.student_conversation_threads,
  public.student_conversation_messages, public.student_conversation_preferences to service_role;

create policy student_conversation_threads_owner_read on public.student_conversation_threads
for select to authenticated using (
  owner_user_id = (select auth.uid()) and exists (
    select 1 from public.student_academic_profiles p
    join public.study_plans sp on sp.id = p.study_plan_id
    join public.majors m on m.id = sp.major_id
    join public.faculties f on f.id = m.faculty_id
    where p.id = profile_id and p.owner_user_id = (select auth.uid())
      and f.university_id = institution_id
  )
);
create policy student_conversation_messages_owner_read on public.student_conversation_messages
for select to authenticated using (
  owner_user_id = (select auth.uid()) and exists (
    select 1 from public.student_conversation_threads t
    where t.id = thread_id and t.owner_user_id = (select auth.uid())
      and t.institution_id = student_conversation_messages.institution_id
  )
);
create policy student_conversation_preferences_owner_read on public.student_conversation_preferences
for select to authenticated using (
  owner_user_id = (select auth.uid()) and exists (
    select 1 from public.student_academic_profiles p
    join public.study_plans sp on sp.id = p.study_plan_id
    join public.majors m on m.id = sp.major_id
    join public.faculties f on f.id = m.faculty_id
    where p.owner_user_id = (select auth.uid()) and f.university_id = institution_id
  )
);

revoke all on function public.validate_student_conversation_scope() from public, anon, authenticated;
revoke all on function public.validate_student_conversation_preference_scope() from public, anon, authenticated;
grant execute on function public.validate_student_conversation_scope() to service_role;
grant execute on function public.validate_student_conversation_preference_scope() to service_role;
