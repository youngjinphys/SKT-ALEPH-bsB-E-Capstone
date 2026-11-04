-- Isolated SQL behavior check derived from migration 002; executed on PostgreSQL 17.
-- Uses session-local objects and a synthetic authorize stub, then ROLLBACK.
-- Does not verify production capability/RLS grants, HTTP transport, or multi-connection concurrency.
-- Run on the operations database. No credentials or user identifiers are stored.
-- All workers use one locked row: global rolling 5/minute AND 30/hour ceilings.
begin;
create temporary table test_auth_attempts (
 id boolean primary key default true check(id),
 attempted_at timestamptz[] not null default '{}'
);
insert into pg_temp.test_auth_attempts(id) values(true) on conflict do nothing;
create temporary table test_auth_sessions (
 token_hash text primary key check(token_hash ~ '^[a-f0-9]{64}$'),
 config_version text not null check(config_version ~ '^[a-f0-9]{64}$'), expires_at timestamptz not null
);
alter table pg_temp.test_auth_attempts enable row level security;
alter table pg_temp.test_auth_sessions enable row level security;
create function pg_temp.authorize(capability text) returns void language plpgsql as $$ begin if capability is distinct from 'isolated-test-only' then raise insufficient_privilege; end if; end; $$;
create or replace function pg_temp.aleph_test_auth_attempt(capability text) returns boolean
language plpgsql security definer set search_path='' as $$
declare a pg_temp.test_auth_attempts; v_now timestamptz;
begin
 perform pg_temp.authorize(capability);
 select * into strict a from pg_temp.test_auth_attempts where id for update;
 v_now := clock_timestamp();
 select coalesce(array_agg(t), '{}'::timestamptz[]) into a.attempted_at
 from unnest(a.attempted_at) t where t > v_now - interval '1 hour';
 if cardinality(a.attempted_at) >= 30 or
    (select count(*) from unnest(a.attempted_at) t where t > v_now - interval '1 minute') >= 5
 then return false; end if;
 update pg_temp.test_auth_attempts set attempted_at=array_append(a.attempted_at,v_now) where id;
 return true;
end; $$;
create or replace function pg_temp.aleph_test_auth_session(capability text, operation text, token_hash text,
 config_version text, lifetime_seconds integer) returns boolean
language plpgsql security definer set search_path='' as $$
begin
 perform pg_temp.authorize(capability);
 if token_hash is null or token_hash !~ '^[a-f0-9]{64}$' then return false; end if;
 if operation='delete' then
  delete from pg_temp.test_auth_sessions s where s.token_hash=aleph_test_auth_session.token_hash;
  return true;
 end if;
 if config_version is null or config_version !~ '^[a-f0-9]{64}$' then return false; end if;
 if operation='check' then
  return exists(select 1 from pg_temp.test_auth_sessions s where s.token_hash=aleph_test_auth_session.token_hash
    and s.config_version=aleph_test_auth_session.config_version and s.expires_at>clock_timestamp());
 elsif operation='create' then
  if lifetime_seconds is null or lifetime_seconds<1 or lifetime_seconds>900 then return false; end if;
  delete from pg_temp.test_auth_sessions s where s.expires_at<=clock_timestamp();
  insert into pg_temp.test_auth_sessions values(token_hash,config_version,clock_timestamp()+make_interval(secs=>lifetime_seconds));
  return true;
 end if;
 return false;
end; $$;
do $$ declare i integer; ok boolean; begin
 for i in 1..5 loop if not pg_temp.aleph_test_auth_attempt('isolated-test-only') then raise exception 'attempt rejected early'; end if; end loop;
 if pg_temp.aleph_test_auth_attempt('isolated-test-only') then raise exception 'sixth attempt accepted'; end if;
 update pg_temp.test_auth_attempts set attempted_at=array_fill(clock_timestamp()-interval '2 minutes',array[30]);
 if pg_temp.aleph_test_auth_attempt('isolated-test-only') then raise exception 'hour ceiling exceeded'; end if;
 update pg_temp.test_auth_attempts set attempted_at=array_fill(clock_timestamp()-interval '2 hours',array[30]);
 if not pg_temp.aleph_test_auth_attempt('isolated-test-only') then raise exception 'expired window not released'; end if;
 begin perform pg_temp.aleph_test_auth_attempt('bad'); raise exception 'bad capability accepted'; exception when insufficient_privilege then null; end;
 if pg_temp.aleph_test_auth_session('isolated-test-only','create',repeat('a',64),repeat('b',64),901) then raise exception 'TTL accepted'; end if;
 if not pg_temp.aleph_test_auth_session('isolated-test-only','create',repeat('a',64),repeat('b',64),900) then raise exception 'create failed'; end if;
 if not pg_temp.aleph_test_auth_session('isolated-test-only','check',repeat('a',64),repeat('b',64),0) then raise exception 'check failed'; end if;
 if pg_temp.aleph_test_auth_session('isolated-test-only','check',repeat('a',64),repeat('c',64),0) then raise exception 'rotation failed'; end if;
 perform pg_temp.aleph_test_auth_session('isolated-test-only','delete',repeat('a',64),'',0);
 if pg_temp.aleph_test_auth_session('isolated-test-only','check',repeat('a',64),repeat('b',64),0) then raise exception 'logout failed'; end if;
end; $$;
select 'PASS: rolling windows, incorrect capability rejection, TTL bounds, session lifecycle and rotation; isolated temporary objects only' as result;
rollback;
