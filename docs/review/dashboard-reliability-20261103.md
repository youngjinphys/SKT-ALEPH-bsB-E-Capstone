# Operator dashboard: lifecycle, capacity and responsive audit

## Scope and judgment

Baseline `44e40ca1059e8f01fba30f7c370912eee06c0c8a` includes a shared local console and a same-project Vercel `/dashboard` adapter. Existing evidence freshness checks, independent signing, explicit publication and signed DNS status are retained. No new Vercel project, credentials, DB migration or automated policy approval is introduced.

The separation between preview and commit is sound, but the original browser code guarded only HTTP requests. A `File.text()` operation could outlive login or a file/target change and subsequently submit data under a new context. Separate regressions reproduced this behavior before the fix.

## Implemented corrections

- Bind the entire upload/preview/confirmation operation to session epoch, view epoch, selected file and form revision. Changing a target/file or navigating away invalidates the preview; locking disables commit buttons immediately. A request already sent may still commit server-side, so the persisted audit remains the source of truth after disconnection.
- Append the **server-verified operator email**, action and target state revision in the same compare-and-swap snapshot as a successful cloud mutation. User-entered reviewer names remain review notes, not authentication. Failed CAS and read-only previews do not persist successful mutation records. These records are not tamper-proof external audit evidence.
- Make authenticated capability discovery independent of state-store availability. Add operator-only, read-only snapshot capacity diagnostics. Its exact serialized JSON byte budget and file count match the existing 8 MiB / 512-file enforcement; 75% and 90% thresholds flag approaching limits. No raw paths, evidence URLs or keys are returned. Provider outage yields an error, not empty/healthy statistics.
- Show capacity in the cloud audit view with labelled meters and category counts. On lookup failure or logout, previous normal values are hidden. Do not automatically prune evidence, key history or replay counters; retention/export remains a deliberate maintenance operation.
- Retain the navy/cyan design language while reducing decorative header height. Mobile shows all six navigation actions with 44px targets, a compact toolbar and policy status before decorative content. Fluid table columns avoid 320px overflow. Existing native confirmation dialog, focus states, reduced-motion and forced-colors fallbacks remain.

## Verification evidence

Local checks use an archived tracked-source snapshot from GitHub CI, with a pinned source SHA. No production secrets or sessions are used. Regression tests exercise delayed file reads, in-flight file/target changes, reauthentication, view changes, authenticated actor provenance, storage failures, privacy and exact capacity accounting.

Browser acceptance runs both local and cloud adapters against real loopback HTTP handlers and synthetic data. It checks preview/cancel/import, approval reset, node search/filter, lock, storage read/failure and responsive layouts at 320, 390 and 768px plus desktop. Navigation target geometry and mobile policy-status visibility are asserted; screenshots and `results.json` are produced. This is not a claim of complete WCAG certification or production network acceptance.

CI stores the public tracked source archive and commit identifier alongside screenshots for reproducibility (seven-day retention, no environment/credentials or untracked files). Verify the final commit's workflows before deployment.

## Operational boundaries

No live Google/OpenPhish credential calls, production Supabase mutation, real TLS/vhost installation or LAN DNS enforcement is performed by the offline browser suite. The cloud UI still imports independently collected evidence rather than running a root/long-lived collector inside serverless requests. Signed publication is not proof that LAN clients use the desired resolver. Capacity warnings do not expand backend limits or implement archive retention. Keep the external signing and on-site validation procedures.
