-- SOMENTE LEITURA: nao recria a migracao, nao altera roles, dados ou permissoes.
-- Executar no SQL Editor do projeto como administrador.
with checks(verificacao, ok) as (
    values
    ('01 Dependencia auth.users', to_regclass('auth.users') is not null),
    ('02 Dependencia auth.uid()', to_regprocedure('auth.uid()') is not null),
    ('03 Tabela public.vibration_sources', exists (
        select 1 from pg_class where oid=to_regclass('public.vibration_sources') and relkind='r')),
    ('04 Tabela public.vibration_objects', exists (
        select 1 from pg_class where oid=to_regclass('public.vibration_objects') and relkind='r')),
    ('05 RLS habilitada nas duas tabelas', (
        select count(*)=2 and bool_and(relrowsecurity) from pg_class
        where oid in (to_regclass('public.vibration_sources'),to_regclass('public.vibration_objects')))),
    ('06 Colunas e tipos de vibration_sources', (
        select array_agg(attname::text||'='||format_type(atttypid,atttypmod) order by attnum)
            =array['id=uuid','writer_uid=uuid','label=text','published=boolean']
        from pg_attribute where attrelid=to_regclass('public.vibration_sources') and attnum>0 and not attisdropped)),
    ('07 Colunas e tipos de vibration_objects', (
        select array_agg(attname::text||'='||format_type(atttypid,atttypmod) order by attnum)
            =array['source_id=uuid','kind=text','entity_id=text','payload=jsonb','content_hash=text','revision=bigint','received_at=timestamp with time zone']
        from pg_attribute where attrelid=to_regclass('public.vibration_objects') and attnum>0 and not attisdropped)),
    ('08 Chave primaria de vibration_sources', exists (
        select 1 from pg_constraint where conrelid=to_regclass('public.vibration_sources')
        and contype='p' and pg_get_constraintdef(oid)='PRIMARY KEY (id)')),
    ('09 Chave primaria composta dos objetos', exists (
        select 1 from pg_constraint where conrelid=to_regclass('public.vibration_objects')
        and contype='p' and pg_get_constraintdef(oid)='PRIMARY KEY (source_id, kind, entity_id)')),
    ('10 FK do escritor para auth.users', exists (
        select 1 from pg_constraint where conrelid=to_regclass('public.vibration_sources') and contype='f'
        and confrelid=to_regclass('auth.users') and conkey=array[2]::smallint[])),
    ('11 FK dos objetos para a origem', exists (
        select 1 from pg_constraint where conrelid=to_regclass('public.vibration_objects') and contype='f'
        and confrelid=to_regclass('public.vibration_sources') and conkey=array[1]::smallint[])),
    ('12 Cinco CHECKs nos objetos', (
        select count(*)=5 from pg_constraint where conrelid=to_regclass('public.vibration_objects') and contype='c')),
    ('13 Origens novas com published=false', exists (
        select 1 from pg_attribute a join pg_attrdef d on d.adrelid=a.attrelid and d.adnum=a.attnum
        where a.attrelid=to_regclass('public.vibration_sources') and a.attname='published'
        and pg_get_expr(d.adbin,d.adrelid)='false')),
    ('14 Nenhuma policy na tabela de escritores', (
        select count(*)=0 from pg_policy where polrelid=to_regclass('public.vibration_sources'))),
    ('15 Apenas a policy SELECT esperada nos objetos', (
        select count(*)=1 and bool_and(polname='vibration_public_read' and polcmd='r' and polpermissive
            and polroles @> array[(select oid from pg_roles where rolname='anon'),
                                 (select oid from pg_roles where rolname='authenticated')]::oid[]
            and array_length(polroles,1)=2
            and position('vibration_is_public(source_id)' in pg_get_expr(polqual,polrelid))>0)
        from pg_policy where polrelid=to_regclass('public.vibration_objects'))),
    ('16 RPC e helper com assinaturas esperadas',
        to_regprocedure('public.vibration_sync_batch(uuid,jsonb)') is not null
        and to_regprocedure('public.vibration_is_public(uuid)') is not null),
    ('17 Funcoes SECURITY DEFINER com search_path vazio', (
        select count(*)=2 and bool_and(prosecdef and proconfig @> array['search_path=""'])
        from pg_proc where oid in (to_regprocedure('public.vibration_sync_batch(uuid,jsonb)'),
                                  to_regprocedure('public.vibration_is_public(uuid)')))),
    ('18 anon sem acesso direto a vibration_sources', not (
        has_table_privilege('anon',to_regclass('public.vibration_sources'),'SELECT') or
        has_table_privilege('anon',to_regclass('public.vibration_sources'),'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))),
    ('19 authenticated sem acesso direto a vibration_sources', not (
        has_table_privilege('authenticated',to_regclass('public.vibration_sources'),'SELECT') or
        has_table_privilege('authenticated',to_regclass('public.vibration_sources'),'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))),
    ('20 anon pode SELECT nos objetos, sujeito a RLS',
        has_table_privilege('anon',to_regclass('public.vibration_objects'),'SELECT')),
    ('21 authenticated pode SELECT nos objetos, sujeito a RLS',
        has_table_privilege('authenticated',to_regclass('public.vibration_objects'),'SELECT')),
    ('22 anon sem escrita direta nos objetos', not
        has_table_privilege('anon',to_regclass('public.vibration_objects'),'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')),
    ('23 authenticated sem escrita direta nos objetos', not
        has_table_privilege('authenticated',to_regclass('public.vibration_objects'),'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')),
    ('24 anon sem EXECUTE na RPC de escrita', not
        has_function_privilege('anon',to_regprocedure('public.vibration_sync_batch(uuid,jsonb)'),'EXECUTE')),
    ('25 authenticated com EXECUTE na RPC de escrita',
        has_function_privilege('authenticated',to_regprocedure('public.vibration_sync_batch(uuid,jsonb)'),'EXECUTE')),
    ('26 anon com EXECUTE no helper de leitura',
        has_function_privilege('anon',to_regprocedure('public.vibration_is_public(uuid)'),'EXECUTE')),
    ('27 authenticated com EXECUTE no helper de leitura',
        has_function_privilege('authenticated',to_regprocedure('public.vibration_is_public(uuid)'),'EXECUTE')),
    ('28 Funcoes sem EXECUTE concedido a PUBLIC', not exists (
        select 1 from pg_proc p cross join lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
        where p.oid in (to_regprocedure('public.vibration_sync_batch(uuid,jsonb)'),
                        to_regprocedure('public.vibration_is_public(uuid)'))
        and a.grantee=0 and a.privilege_type='EXECUTE'))
)
select verificacao, case when coalesce(ok,false) then 'OK' else 'REVISAR' end as resultado
from checks order by verificacao;
