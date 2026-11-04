-- Run on the operations database. No credentials or user identifiers are stored.
-- All workers use one locked row: global rolling 5/minute AND 30/hour ceilings.
begin;
create table if not exists aleph_ops_private.test_auth_attempts (
 id boolean primary key default true check(id),
 attempted_at timestamptz[] not null default '{}'
);
insert into aleph_ops_private.test_auth_attempts(id) values(true) on conflict do nothing;
create table if not exists aleph_ops_private.test_auth_sessions (
 token_hash text primary key check(token_hash ~ '^[a-f0-9]{64}$'),
 config_version text not null check(config_version ~ '^[a-f0-9]{64}$'), expires_at timestamptz not null
);
alter table aleph_ops_private.test_auth_attempts enable row level security;
alter table aleph_ops_private.test_auth_sessions enable row level security;
revoke all on aleph_ops_private.test_auth_attempts, aleph_ops_private.test_auth_sessions from public,anon,authenticated;
create or replace function public.aleph_test_auth_attempt(capability text) returns boolean
language plpgsql security definer set search_path='' as $$
declare a aleph_ops_private.test_auth_attempts; v_now timestamptz;
begin
 perform aleph_ops_private.authorize(capability);
 select * into strict a from aleph_ops_private.test_auth_attempts where id for update;
 v_now := clock_timestamp();
 select coalesce(array_agg(t), '{}'::timestamptz[]) into a.attempted_at
 from unnest(a.attempted_at) t where t > v_now - interval '1 hour';
 if cardinality(a.attempted_at) >= 30 or
    (select count(*) from unnest(a.attempted_at) t where t > v_now - interval '1 minute') >= 5
 then return false; end if;
 update aleph_ops_private.test_auth_attempts set attempted_at=array_append(a.attempted_at,v_now) where id;
 return true;
end; $$;
create or replace function public.aleph_test_auth_session(capability text, operation text, token_hash text,
 config_version text, lifetime_seconds integer) returns boolean
language plpgsql security definer set search_path='' as $$
begin
 perform aleph_ops_private.authorize(capability);
 if token_hash is null or token_hash !~ '^[a-f0-9]{64}$' then return false; end if;
 if operation='delete' then
  delete from aleph_ops_private.test_auth_sessions s where s.token_hash=aleph_test_auth_session.token_hash;
  return true;
 end if;
 if config_version is null or config_version !~ '^[a-f0-9]{64}$' then return false; end if;
 if operation='check' then
  return exists(select 1 from aleph_ops_private.test_auth_sessions s where s.token_hash=aleph_test_auth_session.token_hash
    and s.config_version=aleph_test_auth_session.config_version and s.expires_at>clock_timestamp());
 elsif operation='create' then
  if lifetime_seconds is null or lifetime_seconds<1 or lifetime_seconds>900 then return false; end if;
  delete from aleph_ops_private.test_auth_sessions s where s.expires_at<=clock_timestamp();
  insert into aleph_ops_private.test_auth_sessions values(token_hash,config_version,clock_timestamp()+make_interval(secs=>lifetime_seconds));
  return true;
 end if;
 return false;
end; $$;
revoke all on function public.aleph_test_auth_attempt(text) from public;
revoke all on function public.aleph_test_auth_session(text,text,text,text,integer) from public;
grant execute on function public.aleph_test_auth_attempt(text) to anon,authenticated;
grant execute on function public.aleph_test_auth_session(text,text,text,text,integer) to anon,authenticated;
commit;
