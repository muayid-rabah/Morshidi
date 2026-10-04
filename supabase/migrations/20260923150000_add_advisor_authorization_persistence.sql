-- Phase P7.4: Advisor authorization and explicit advisor-student assignment persistence.
-- Minimal, server-managed assignment foundation; target_period_id is excluded by design.

-- 1. Extend institutional_memberships role check constraint to accept ACADEMIC_ADVISOR
alter table public.institutional_memberships
  drop constraint if exists institutional_memberships_role_check,
  add constraint institutional_memberships_role_check
    check (role in ('INSTITUTIONAL_ANALYST', 'ACADEMIC_ADVISOR'));

-- 2. Create advisor_student_assignments table
create table public.advisor_student_assignments (
  id uuid primary key default gen_random_uuid(),
  advisor_user_id uuid not null references auth.users(id) on delete restrict,
  student_user_id uuid not null references auth.users(id) on delete restrict,
  university_id uuid not null references public.universities(id) on delete restrict,
  is_active boolean not null default true,
  authority_source text not null check (btrim(authority_source) <> ''),
  authority_version text not null check (btrim(authority_version) <> ''),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint check_advisor_student_distinct check (advisor_user_id <> student_user_id)
);

-- 3. Uniqueness and Lookup Indexes
-- Prevent duplicate active authority records for the same advisor-student-university relationship
create unique index idx_advisor_student_assignments_active_unique
  on public.advisor_student_assignments (advisor_user_id, student_user_id, university_id)
  where is_active;

-- Fast exact lookup index for authorization queries
create index idx_advisor_student_assignments_lookup
  on public.advisor_student_assignments (advisor_user_id, student_user_id, university_id, is_active);

-- 4. Triggers
create trigger set_advisor_student_assignment_updated_at
  before update on public.advisor_student_assignments
  for each row execute function public.set_updated_at();

-- 5. Row Level Security & Grants
alter table public.advisor_student_assignments enable row level security;

-- Revoke all permissions from public, anon, and authenticated
revoke all on table public.advisor_student_assignments
  from public, anon, authenticated, service_role;

-- Grant service_role full control for trusted server-side authorization and provisioning
grant select, insert, update, delete on table public.advisor_student_assignments
  to service_role;

-- Zero policies for anon or authenticated: all reads and mutations occur via server-side service_role.

-- 6. Comments
comment on table public.advisor_student_assignments is
  'P7.4 server-authoritative explicit advisor-to-student assignment relations; planning periods excluded.';
