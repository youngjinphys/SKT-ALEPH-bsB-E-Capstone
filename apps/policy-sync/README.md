# Signed Policy Sync

Unprivileged HTTPS fetch + Ed25519-verified, root-only local policy publication.
Repeated signed sequences require a **read-only live DNS attestation**
(policy file SHA, agent acknowledgement, health response and nftables guard)
before returning `already-applied`. The root apply step durably saves a
**pending intent before DNS publication** and only commits the sequence
watermark after the DNS publisher reports successful application.
Interrupted releases may be safely retried. If the inbox advances, the
root verifier reconciles the pending or previously committed live DNS policy
before applying a newer signed release. If neither can be verified, processing
stops and the pending journal remains for inspection. Recovery never extends the original policy TTL. Operators must pause automatic
fetch/apply timers during an emergency policy override; a newly signed policy
remains eligible for ordinary automated enforcement once timers resume.
Does not perform DNS queries, score threat intelligence, deploy databases,
or modify firewall/DHCP. **No real policy is downloaded or applied by CI tests.**

Read the [Korean setup and recovery guide](../../docs/policy-distribution.md).

`python3 -m aleph_policy_sync {key-id,sign,verify,fetch,apply} --help`

Requires Python >=3.11, `cryptography>=41`, and the existing `dns_agent.policy`
contract on `PYTHONPATH`. Signing keys must be held outside GitHub and the
published HTTPS root. No runtime remote API/database dependency in DNS.
