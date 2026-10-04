-- WC-038 semantic retrieval foundation. Embeddings are trusted backend infrastructure only.
create extension if not exists vector with schema extensions;

create table public.policy_passage_embeddings (
  id uuid primary key default gen_random_uuid(),
  passage_id uuid not null references public.policy_passages(id) on delete cascade,
  embedding extensions.vector(1536) not null,
  provider text not null check (pg_catalog.btrim(provider) <> ''),
  model text not null check (pg_catalog.btrim(model) <> ''),
  dimensions integer not null check (dimensions = 1536),
  source_content_sha256 text not null check (source_content_sha256 ~ '^[0-9a-f]{64}$'),
  embedded_at timestamptz not null default pg_catalog.now(),
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now(),
  constraint uq_policy_passage_embeddings_passage_provider_model unique (passage_id, provider, model)
);

create index idx_policy_passage_embeddings_vector_cosine
  on public.policy_passage_embeddings using hnsw (embedding extensions.vector_cosine_ops);

create index idx_policy_passage_embeddings_passage
  on public.policy_passage_embeddings (passage_id);

create trigger set_policy_passage_embeddings_updated_at
  before update on public.policy_passage_embeddings
  for each row execute function public.set_updated_at();

alter table public.policy_passage_embeddings enable row level security;
revoke all on table public.policy_passage_embeddings from public, anon, authenticated;
grant all on table public.policy_passage_embeddings to service_role;

create or replace function public.search_verified_policy_passages_semantic(
  p_university_id uuid,
  p_query_embedding extensions.vector(1536),
  p_provider text,
  p_model text,
  p_limit integer default 10,
  p_category text default null,
  p_document_id uuid default null
)
returns table (
  document_id uuid,
  document_code text,
  document_title text,
  category text,
  version_id uuid,
  version_tag text,
  status text,
  effective_start_date timestamptz,
  effective_end_date timestamptz,
  content_sha256 text,
  verified_at timestamptz,
  verified_by text,
  source_url text,
  passage_id uuid,
  sequence_order integer,
  passage_text text,
  locator_text text,
  article_number text,
  section_number text,
  page_number integer,
  heading text,
  passage_sha256 text,
  semantic_similarity double precision
)
language sql
security definer
set search_path = ''
as $$
  select
    d.id, d.document_code, d.title, d.category,
    v.id, v.version_tag, v.status, v.effective_start_date, v.effective_end_date,
    v.content_sha256, v.verified_at, v.verified_by, v.source_url,
    p.id, p.sequence_order, p.passage_text, p.locator_text,
    p.article_number, p.section_number, p.page_number, p.heading, p.passage_sha256,
    1 - (e.embedding OPERATOR(extensions.<=>) p_query_embedding) as semantic_similarity
  from public.policy_passage_embeddings e
  join public.policy_passages p on p.id = e.passage_id
  join public.policy_document_versions v on v.id = p.version_id
  join public.policy_documents d on d.id = v.document_id
  where d.university_id = p_university_id
    and pg_catalog.lower(v.status) = 'verified'
    and v.effective_start_date <= pg_catalog.now()
    and (v.effective_end_date is null or v.effective_end_date > pg_catalog.now())
    and e.provider = p_provider
    and e.model = p_model
    and e.dimensions = 1536
    and e.source_content_sha256 = p.passage_sha256
    and (p_category is null or d.category = p_category)
    and (p_document_id is null or d.id = p_document_id)
  order by e.embedding OPERATOR(extensions.<=>) p_query_embedding asc,
    d.document_code asc, p.sequence_order asc, p.id asc
  limit least(greatest(p_limit, 1), 20);
$$;

revoke all on function public.search_verified_policy_passages_semantic(
  uuid, extensions.vector, text, text, integer, text, uuid
) from public, anon, authenticated;
grant execute on function public.search_verified_policy_passages_semantic(
  uuid, extensions.vector, text, text, integer, text, uuid
) to service_role;

-- Keyset-paged source for the explicit trusted backfill command. Never callable by students.
create or replace function public.list_verified_policy_embedding_candidates(
  p_provider text,
  p_model text,
  p_after_passage_id uuid default null,
  p_limit integer default 50,
  p_document_id uuid default null
)
returns table (
  passage_id uuid,
  passage_text text,
  passage_sha256 text,
  existing_source_content_sha256 text,
  existing_dimensions integer
)
language sql
security definer
set search_path = ''
as $$
  select p.id, p.passage_text, p.passage_sha256,
    e.source_content_sha256, e.dimensions
  from public.policy_passages p
  join public.policy_document_versions v on v.id = p.version_id
  join public.policy_documents d on d.id = v.document_id
  left join public.policy_passage_embeddings e
    on e.passage_id = p.id and e.provider = p_provider and e.model = p_model
  where pg_catalog.lower(v.status) = 'verified'
    and v.effective_start_date <= pg_catalog.now()
    and (v.effective_end_date is null or v.effective_end_date > pg_catalog.now())
    and p.passage_sha256 is not null
    and (p_after_passage_id is null or p.id > p_after_passage_id)
    and (p_document_id is null or d.id = p_document_id)
  order by p.id
  limit least(greatest(p_limit, 1), 100);
$$;

revoke all on function public.list_verified_policy_embedding_candidates(
  text, text, uuid, integer, uuid
) from public, anon, authenticated;
grant execute on function public.list_verified_policy_embedding_candidates(
  text, text, uuid, integer, uuid
) to service_role;
