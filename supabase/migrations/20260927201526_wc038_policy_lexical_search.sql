-- WC-038 deterministic lexical retrieval. This RPC is backend-only.
create or replace function public.search_verified_policy_passages(
  p_university_id uuid,
  p_query text,
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
  score integer
)
language sql
security definer
set search_path = ''
as $$
  with normalized as (
    select pg_catalog.lower(pg_catalog.regexp_replace(pg_catalog.btrim(p_query), '\s+', ' ', 'g')) as query_text
  ),
  tokens as (
    select distinct token
    from normalized, pg_catalog.regexp_split_to_table(query_text, '\s+') as token
    where pg_catalog.char_length(token) >= 2
  ),
  candidates as (
    select
      d.id as document_id, d.document_code, d.title as document_title, d.category,
      v.id as version_id, v.version_tag, v.status, v.effective_start_date, v.effective_end_date,
      v.content_sha256, v.verified_at, v.verified_by, v.source_url,
      p.id as passage_id, p.sequence_order, p.passage_text, p.locator_text,
      p.article_number, p.section_number, p.page_number, p.heading, p.passage_sha256,
      pg_catalog.lower(pg_catalog.concat_ws(' ', p.passage_text, p.locator_text, p.article_number, p.section_number,
        p.heading, d.title, d.document_code)) as searchable_text
    from public.policy_documents d
    join public.policy_document_versions v on v.document_id = d.id
    join public.policy_passages p on p.version_id = v.id
    where d.university_id = p_university_id
      and pg_catalog.lower(v.status) = 'verified'
      and v.effective_start_date <= pg_catalog.now()
      and (v.effective_end_date is null or v.effective_end_date > pg_catalog.now())
      and (p_category is null or d.category = p_category)
      and (p_document_id is null or d.id = p_document_id)
  ),
  scored as (
    select c.*, (select pg_catalog.count(*) from tokens) as token_count,
      (select pg_catalog.count(*) from tokens t where c.searchable_text like '%' || t.token || '%') as matched_token_count,
      (
      case when c.searchable_text like '%' || n.query_text || '%' then 100 else 0 end
      + case when pg_catalog.lower(c.passage_text) like '%' || n.query_text || '%' then 40 else 0 end
      + 10 * (select pg_catalog.count(*) from tokens t where c.searchable_text like '%' || t.token || '%')
    )::integer as score
    from candidates c cross join normalized n
  )
  select document_id, document_code, document_title, category, version_id, version_tag, status,
    effective_start_date, effective_end_date, content_sha256, verified_at, verified_by, source_url,
    passage_id, sequence_order, passage_text, locator_text, article_number, section_number,
    page_number, heading, passage_sha256, score
  from scored
  where score > 0
    and (score >= 100 or matched_token_count * 2 >= token_count)
  order by score desc, document_code asc, sequence_order asc, passage_id asc
  limit least(greatest(p_limit, 1), 20);
$$;

revoke all on function public.search_verified_policy_passages(uuid, text, integer, text, uuid)
  from public, anon, authenticated;
grant execute on function public.search_verified_policy_passages(uuid, text, integer, text, uuid)
  to service_role;
