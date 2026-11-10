-- Aplicar pelo SQL Editor como administrador. Sem alteracao de tabelas existentes.
begin;
create table if not exists public.vibration_sources (
    id uuid primary key,
    writer_uid uuid not null references auth.users(id),
    label text not null default 'Bancada acadêmica',
    published boolean not null default false
);
alter table public.vibration_sources enable row level security;
revoke all on public.vibration_sources from public, anon, authenticated;

create table if not exists public.vibration_objects (
    source_id uuid not null references public.vibration_sources(id),
    kind text not null check(kind in ('measurement','session','membership','event','model','score','status')),
    entity_id text not null check(length(entity_id) between 1 and 128),
    payload jsonb not null check(jsonb_typeof(payload)='object' and octet_length(payload::text)<16384),
    content_hash text not null check(content_hash ~ '^[0-9a-f]{64}$'),
    revision bigint not null check(revision>0),
    received_at timestamptz not null default now(),
    primary key(source_id,kind,entity_id)
);
alter table public.vibration_objects enable row level security;
revoke all on public.vibration_objects from public, anon, authenticated;
grant select on public.vibration_objects to anon, authenticated;

create or replace function public.vibration_is_public(p_source uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists(select 1 from public.vibration_sources where id=p_source and published);
$$;
revoke all on function public.vibration_is_public(uuid) from public;
grant execute on function public.vibration_is_public(uuid) to anon, authenticated;
drop policy if exists vibration_public_read on public.vibration_objects;
create policy vibration_public_read on public.vibration_objects for select to anon, authenticated
    using(public.vibration_is_public(source_id));

create or replace function public.vibration_sync_batch(p_source uuid,p_items jsonb) returns integer
language plpgsql security definer set search_path = '' as $$
declare item jsonb; allowed text[]; k text; old_hash text; old_revision bigint;
begin
    if auth.uid() is null or not exists(select 1 from public.vibration_sources
        where id=p_source and writer_uid=auth.uid()) then
        raise exception 'writer not authorized' using errcode='42501';
    end if;
    if jsonb_typeof(p_items) is distinct from 'array' or jsonb_array_length(p_items) not between 1 and 200 then
        raise exception 'invalid batch';
    end if;
    for item in select value from jsonb_array_elements(p_items) loop
        k:=item->>'kind';
        allowed:=case k
            when 'measurement' then array['id','instante','pico_fft','amplitude','rms','atrasos','origem']
            when 'session' then array['id','experimento_id','codigo','estado','inicio','fim','meta_registros']
            when 'membership' then array['medicao_id','sessao_id','elegivel','motivo_exclusao']
            when 'event' then array['id','sessao_id','inicio','fim']
            when 'model' then array['id','comparacao_id','experimento_id','sessao_treino_id','variante','criado_em','dados_sha256','artefato_sha256']
            when 'score' then array['modelo_id','medicao_id','sessao_id','papel','score_bruto','score_decisao','alerta','calculado_em']
            when 'status' then array['last_success_at','pending','failed','checked_at']
            else null end;
        if allowed is null or jsonb_typeof(item->'payload') is distinct from 'object'
            or not (item->'payload' ?& allowed) or (item->'payload')-allowed <> '{}'::jsonb then
            raise exception 'payload outside public contract';
        end if;
        if k='measurement' and (item->'payload'->>'origem') is distinct from 'real' then
            raise exception 'only real measurements allowed';
        end if;
        insert into public.vibration_objects(source_id,kind,entity_id,payload,content_hash,revision)
        values(p_source,k,item->>'entity_id',item->'payload',item->>'content_hash',(item->>'revision')::bigint)
        on conflict(source_id,kind,entity_id) do update
            set payload=excluded.payload,content_hash=excluded.content_hash,revision=excluded.revision,received_at=now()
            where public.vibration_objects.revision < excluded.revision;
        select content_hash,revision into old_hash,old_revision from public.vibration_objects
            where source_id=p_source and kind=k and entity_id=item->>'entity_id';
        if old_revision=(item->>'revision')::bigint and old_hash<>item->>'content_hash' then
            raise exception 'revision collision; preserve local queue';
        end if;
    end loop;
    return jsonb_array_length(p_items);
end;
$$;
revoke all on function public.vibration_sync_batch(uuid,jsonb) from public,anon;
grant execute on function public.vibration_sync_batch(uuid,jsonb) to authenticated;
commit;
