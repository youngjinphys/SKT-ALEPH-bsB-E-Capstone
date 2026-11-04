# Stored server DNS terminal view

## Evidence and boundaries

The displayed terminal is a non-executing selection of the eight real server-host queries captured on 2026-11-04 at 02:42:20–24 UTC. It is not a new run, an interactive shell, or the separate 240-observation loopback fixture. The original log SHA-256 is `a3157ec2f8e70c55dda4223073be38b937850ed8bed4d6d0e89e58e96462e87b`.

The JSON was generated from the original log and independently compared field by field: timestamps, commands, header IDs, flags, counts, question, answer TTLs, dig query times, transport and exit code. Endpoint and answer address values are replaced with explicit placeholders. Whitespace is normalized; banners, EDNS, and message-size lines are omitted. All eight responses were NOERROR with addresses. No blocking response was observed for these queries at that time. Current policy, the system stub's downstream resolver and cache use remain unverified. Individual dig times are not a controlled performance comparison.

## Chrome investigation

A fresh temporary headless Google Chrome for Testing 156 profile on server inspected the published prior view. The response charset and document charset were UTF-8; Korean code points were intact. CDP identified system Noto Sans CJK KR for Korean and DejaVu Sans Mono for commands. There were no observed missing glyphs, font-loading failures or console/page errors. Command and response text measured approximately 11.1px and 10.8px. The user's environment-specific cause was not reproduced, so this is not proof that their Chrome issue was caused by encoding or a particular font.

The refactor uses a solid terminal surface, separate UI and ASCII-monospace text, normal wrapping, no text animation, and locally hosted Korean UI font subsets. It no longer relies solely on the viewer's installed Korean font for this view and its mode buttons. The renamed subsets retain the SIL Open Font License and copyright notice; their manifest records source and output hashes and scoped character coverage. No remote font host or security-policy change is required.

## Verification

- Production content, TypeScript and Next.js build passed locally.
- Independent static review verified all eight observations against the original private capture, privacy redactions, font cmap/name/license and native button semantics.
- Unit tests check eight distinct conditions against the separate public excerpt, pinned query times/counts, private-address exclusion, font hashes/required character coverage and no execution/arrow handlers.
- Chromium tests cover all eight records at five viewport sizes, both font weights, readable terminal fields and 60 new choice-click-to-arrow cases. They run within the existing full presentation acceptance suite; a pending run is not a pass.
- The 240-observation fixture view, other slides, original evidence and historical timestamps are not altered by this refactor.
