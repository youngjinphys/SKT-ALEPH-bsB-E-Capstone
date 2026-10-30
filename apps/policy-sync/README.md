# Signed Policy Sync

Unprivileged HTTPS fetch + Ed25519-verified, root-only local policy publication.
Repeated signed sequences now require a **read-only live DNS attestation**
(policy file SHA, agent acknowledgement, health response and nftables guard)
before returning `already-applied`. This avoids reporting success from the
replay watermark alone. No renewed TTL or automatic overwrite is performed.
Does not perform DNS queries, score threat intelligence, deploy databases,
or modify firewall/DHCP. **No real policy is downloaded or applied by CI tests.**

Read the [Korean setup and recovery guide](../../docs/policy-distribution.md).

`python3 -m aleph_policy_sync {key-id,sign,verify,fetch,apply} --help`

Requires Python >=3.11, `cryptography>=41`, and the existing `dns_agent.policy`
contract on `PYTHONPATH`. Signing keys must be held outside GitHub and the
published HTTPS root. No runtime remote API/database dependency in DNS.
