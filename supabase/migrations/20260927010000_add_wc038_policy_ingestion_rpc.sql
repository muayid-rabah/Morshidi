-- Morshidi Phase P8: Atomic Policy Ingestion RPC (WC-038).
-- Forward-only additive migration for single-transaction policy ingestion.

create or replace function public.persist_policy_document_version(
  p_university_id uuid,
  p_document_code text,
  p_title text,
  p_authority_level text,
  p_category text,
  p_language text default 'ar',
  p_version_tag text default '1.0',
  p_effective_start_date timestamptz default now(),
  p_effective_end_date timestamptz default null,
  p_content_sha256 text default '',
  p_status text default 'unverified',
  p_verified_at timestamptz default null,
  p_verified_by text default null,
  p_source_url text default null,
  p_source_snapshot_ref text default null,
  p_passages jsonb default '[]'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
  v_university_exists boolean;
  v_document_id uuid;
  v_version_id uuid;
  v_existing_version_hash text;
  v_existing_version_status text;
  v_passage_item jsonb;
  v_passage_count int := 0;
  v_existing_passage_count int;
  v_created boolean := false;
begin
  -- 1. Validate inputs
  if p_university_id is null then
    raise exception 'university_id cannot be null' using errcode = '23502';
  end if;

  select exists(select 1 from public.universities where id = p_university_id) into v_university_exists;
  if not v_university_exists then
    raise exception 'University % does not exist', p_university_id using errcode = '23503';
  end if;

  if btrim(coalesce(p_document_code, '')) = '' then
    raise exception 'document_code cannot be empty' using errcode = '23514';
  end if;

  if btrim(coalesce(p_title, '')) = '' then
    raise exception 'title cannot be empty' using errcode = '23514';
  end if;

  if btrim(coalesce(p_version_tag, '')) = '' then
    raise exception 'version_tag cannot be empty' using errcode = '23514';
  end if;

  if p_content_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'content_sha256 must be a 64-character lowercase hex string' using errcode = '23514';
  end if;

  -- 2. Upsert / find Document
  select id into v_document_id
  from public.policy_documents
  where university_id = p_university_id and document_code = p_document_code;

  if v_document_id is null then
    insert into public.policy_documents (
      university_id,
      document_code,
      title,
      authority_level,
      category,
      language
    ) values (
      p_university_id,
      p_document_code,
      p_title,
      p_authority_level,
      p_category,
      coalesce(nullif(btrim(p_language), ''), 'ar')
    )
    returning id into v_document_id;
  else
    update public.policy_documents
    set title = p_title,
        authority_level = p_authority_level,
        category = p_category,
        language = coalesce(nullif(btrim(p_language), ''), language),
        updated_at = now()
    where id = v_document_id;
  end if;

  -- 3. Check Version
  select id, content_sha256, status into v_version_id, v_existing_version_hash, v_existing_version_status
  from public.policy_document_versions
  where document_id = v_document_id and version_tag = p_version_tag;

  if v_version_id is not null then
    -- Version exists: check if this is an idempotent match
    if v_existing_version_hash <> p_content_sha256 or lower(v_existing_version_status) <> lower(p_status) then
      raise exception 'Version tag % already exists with differing hash or status for document %', p_version_tag, p_document_code using errcode = '23505';
    end if;

    select count(*) into v_existing_passage_count
    from public.policy_passages
    where version_id = v_version_id;

    -- Return idempotent result
    return jsonb_build_object(
      'document_id', v_document_id,
      'version_id', v_version_id,
      'passage_count', v_existing_passage_count,
      'status', v_existing_version_status,
      'created', false
    );
  end if;

  -- 4. Create new Version
  insert into public.policy_document_versions (
    document_id,
    version_tag,
    effective_start_date,
    effective_end_date,
    content_sha256,
    status,
    verified_at,
    verified_by,
    source_url,
    source_snapshot_ref
  ) values (
    v_document_id,
    p_version_tag,
    coalesce(p_effective_start_date, now()),
    p_effective_end_date,
    p_content_sha256,
    p_status,
    p_verified_at,
    p_verified_by,
    p_source_url,
    p_source_snapshot_ref
  )
  returning id into v_version_id;

  v_created := true;

  -- 5. Insert Passages
  if p_passages is not null and jsonb_typeof(p_passages) = 'array' then
    for v_passage_item in select * from jsonb_array_elements(p_passages)
    loop
      insert into public.policy_passages (
        version_id,
        passage_text,
        locator_text,
        article_number,
        section_number,
        page_number,
        heading,
        sequence_order,
        passage_sha256
      ) values (
        v_version_id,
        v_passage_item->>'passage_text',
        v_passage_item->>'locator_text',
        v_passage_item->>'article_number',
        v_passage_item->>'section_number',
        (v_passage_item->>'page_number')::integer,
        v_passage_item->>'heading',
        coalesce((v_passage_item->>'sequence_order')::integer, v_passage_count),
        v_passage_item->>'passage_sha256'
      );
      v_passage_count := v_passage_count + 1;
    end loop;
  end if;

  return jsonb_build_object(
    'document_id', v_document_id,
    'version_id', v_version_id,
    'passage_count', v_passage_count,
    'status', p_status,
    'created', true
  );
end;
$$;

-- Security & Privileges: Revoke from public/anon/authenticated; Grant exclusively to service_role
revoke all on function public.persist_policy_document_version(
  uuid, text, text, text, text, text, text, timestamptz, timestamptz, text, text, timestamptz, text, text, text, jsonb
) from public, anon, authenticated;

grant execute on function public.persist_policy_document_version(
  uuid, text, text, text, text, text, text, timestamptz, timestamptz, text, text, timestamptz, text, text, text, jsonb
) to service_role;
