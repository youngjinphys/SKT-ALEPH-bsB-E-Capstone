-- Apply once to the selected dedicated operations database (Naver project for production).
-- Provision only SHA256 of a high-entropy production capability afterward.
create schema if not exists aleph_ops_private;
revoke all on schema aleph_ops_private from public, anon, authenticated;
create table if not exists aleph_ops_private.settings(id boolean primary key default true check(id), capability_sha256 text not null check(capability_sha256 ~ '^[a-f0-9]{64}$'));
create table if not exists aleph_ops_private.state(id boolean primary key default true check(id), revision bigint not null default 0 check(revision>=0), value jsonb not null default '{"format":1,"files":{}}', updated_at timestamptz not null default now());
alter table aleph_ops_private.settings enable row level security;
alter table aleph_ops_private.state enable row level security;
revoke all on all tables in schema aleph_ops_private from public, anon, authenticated;
insert into aleph_ops_private.state(id) values(true) on conflict(id) do nothing;
create or replace function aleph_ops_private.authorize(capability text) returns void language plpgsql security definer set search_path='' as $$
begin
 if capability is null or length(capability)<48 or length(capability)>256 or not exists(select 1 from aleph_ops_private.settings s where s.id and s.capability_sha256=encode(sha256(convert_to(capability,'UTF8')),'hex')) then raise insufficient_privilege using message='Invalid operations capability'; end if;
end; $$;
revoke all on function aleph_ops_private.authorize(text) from public,anon,authenticated;
create or replace function public.aleph_ops_load(capability text) returns jsonb language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
 perform aleph_ops_private.authorize(capability);
 select jsonb_build_object('revision',s.revision,'state',s.value) into result from aleph_ops_private.state s where s.id;
 return result;
end; $$;
create or replace function public.aleph_ops_save(capability text,expected_revision bigint,new_state jsonb) returns jsonb language plpgsql security definer set search_path='' as $$
declare next_revision bigint;
begin
 perform aleph_ops_private.authorize(capability);
 if expected_revision is null or expected_revision<0 or new_state is null or jsonb_typeof(new_state) is distinct from 'object' or new_state->'format' is distinct from '1'::jsonb or jsonb_typeof(new_state->'files') is distinct from 'object' or octet_length(new_state::text)>8388608 then raise exception using errcode='22023',message='Invalid or oversized operations state';end if;
 if (select count(*) from jsonb_object_keys(new_state))!=2 or (select count(*) from jsonb_object_keys(new_state->'files'))>512 then raise exception using errcode='22023',message='Unexpected snapshot fields or too many files';end if;
 update aleph_ops_private.state s set revision=s.revision+1,value=new_state,updated_at=clock_timestamp() where s.id and s.revision=expected_revision returning s.revision into next_revision;
 if not found then raise exception using errcode='PT409',message='Concurrent state update';end if;
 return jsonb_build_object('revision',next_revision);
end; $$;
revoke all on function public.aleph_ops_load(text) from public;
revoke all on function public.aleph_ops_save(text,bigint,jsonb) from public;
grant execute on function public.aleph_ops_load(text) to anon,authenticated;
grant execute on function public.aleph_ops_save(text,bigint,jsonb) to anon,authenticated;
