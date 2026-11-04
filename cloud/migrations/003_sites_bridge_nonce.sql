-- Apply only to the existing operations DB. No user identity or key is stored.
begin;
create table if not exists aleph_ops_private.sites_bridge_nonces (
 nonce_hash text primary key check(nonce_hash ~ '^[a-f0-9]{64}$'),
 expires_at timestamptz not null
);
alter table aleph_ops_private.sites_bridge_nonces enable row level security;
revoke all on aleph_ops_private.sites_bridge_nonces from public,anon,authenticated;
create or replace function public.aleph_sites_consume_nonce(capability text, nonce_hash text, expires_epoch bigint)
returns boolean language plpgsql security definer set search_path='' as $$
declare inserted integer; v_now timestamptz := clock_timestamp();
begin
 perform aleph_ops_private.authorize(capability);
 if nonce_hash is null or nonce_hash !~ '^[a-f0-9]{64}$' or expires_epoch is null
    or to_timestamp(expires_epoch)<=v_now or to_timestamp(expires_epoch)>v_now+interval '35 seconds'
 then return false; end if;
 delete from aleph_ops_private.sites_bridge_nonces n where n.expires_at<=v_now;
 insert into aleph_ops_private.sites_bridge_nonces values(nonce_hash,to_timestamp(expires_epoch)) on conflict do nothing;
 get diagnostics inserted = row_count;
 return inserted=1;
end; $$;
revoke all on function public.aleph_sites_consume_nonce(text,text,bigint) from public;
grant execute on function public.aleph_sites_consume_nonce(text,text,bigint) to anon,authenticated;
commit;
