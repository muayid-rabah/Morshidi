-- Morshidi Phase P8: Institutional Policy & University Regulation Persistence (WC-038).
-- Forward-only additive migration for governed policy documents, versions, and passages.

-- 1. Policy Documents Table
create table public.policy_documents (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references public.universities(id) on delete restrict,
  document_code text not null check (btrim(document_code) <> ''),
  title text not null check (btrim(title) <> ''),
  authority_level text not null check (
    lower(authority_level) in (
      'ministry_of_higher_education',
      'university_council',
      'dean_council',
      'faculty_board',
      'department_council'
    )
  ),
  category text not null check (
    lower(category) in (
      'academic_bylaws',
      'registration_regulations',
      'examination_regulations',
      'disciplinary_bylaws',
      'graduation_requirements',
      'credit_transfer_rules'
    )
  ),
  language text not null default 'ar' check (btrim(language) <> ''),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_policy_documents_university_code unique (university_id, document_code)
);

create index idx_policy_documents_university
  on public.policy_documents (university_id);

create index idx_policy_documents_category
  on public.policy_documents (university_id, category);

-- 2. Policy Document Versions Table
create table public.policy_document_versions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.policy_documents(id) on delete restrict,
  version_tag text not null check (btrim(version_tag) <> ''),
  effective_start_date timestamptz not null default now(),
  effective_end_date timestamptz,
  content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
  status text not null check (
    lower(status) in (
      'verified',
      'pending_review',
      'superseded',
      'withdrawn',
      'unverified'
    )
  ),
  verified_at timestamptz,
  verified_by text check (verified_by is null or btrim(verified_by) <> ''),
  source_url text check (source_url is null or btrim(source_url) <> ''),
  source_snapshot_ref text check (source_snapshot_ref is null or btrim(source_snapshot_ref) <> ''),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_policy_versions_document_version unique (document_id, version_tag),
  constraint chk_policy_versions_date_range check (
    effective_end_date is null or effective_end_date >= effective_start_date
  ),
  constraint chk_policy_versions_verification check (
    (lower(status) = 'verified' and verified_at is not null and verified_by is not null and btrim(verified_by) <> '') or
    (lower(status) <> 'verified')
  )
);

create index idx_policy_versions_document
  on public.policy_document_versions (document_id);

create index idx_policy_versions_status
  on public.policy_document_versions (document_id, status);

-- 3. Policy Passages Table
create table public.policy_passages (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.policy_document_versions(id) on delete restrict,
  passage_text text not null check (btrim(passage_text) <> ''),
  locator_text text not null check (btrim(locator_text) <> ''),
  article_number text check (article_number is null or btrim(article_number) <> ''),
  section_number text check (section_number is null or btrim(section_number) <> ''),
  page_number integer check (page_number is null or page_number > 0),
  heading text check (heading is null or btrim(heading) <> ''),
  sequence_order integer not null check (sequence_order >= 0),
  passage_sha256 text check (passage_sha256 is null or passage_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  constraint uq_policy_passages_version_sequence unique (version_id, sequence_order),
  constraint uq_policy_passages_version_locator_seq unique (version_id, locator_text, sequence_order)
);

create index idx_policy_passages_version_order
  on public.policy_passages (version_id, sequence_order);

-- 4. Triggers
create trigger set_policy_documents_updated_at
  before update on public.policy_documents
  for each row execute function public.set_updated_at();

create trigger set_policy_document_versions_updated_at
  before update on public.policy_document_versions
  for each row execute function public.set_updated_at();

-- 5. Row-Level Security & Grants
alter table public.policy_documents enable row level security;
alter table public.policy_document_versions enable row level security;
alter table public.policy_passages enable row level security;

-- Revoke all direct privileges from public, anon, and authenticated roles
revoke all on table public.policy_documents from public, anon, authenticated;
revoke all on table public.policy_document_versions from public, anon, authenticated;
revoke all on table public.policy_passages from public, anon, authenticated;

-- Grant managed persistence operations exclusively to trusted service_role
grant all on table public.policy_documents to service_role;
grant all on table public.policy_document_versions to service_role;
grant all on table public.policy_passages to service_role;
