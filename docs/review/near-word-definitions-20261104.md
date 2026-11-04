# Near-word definition placement

## Root cause

The shared leader router avoided text, but the definition itself stayed in a term-specific top/right/bottom dock outside the diagram. A safe leader could therefore run a long distance across the panel. Routing a line cannot repair the wrong layout location of its endpoint.

## Change

- Render the shared definition in a real layout row immediately after each marked caption or link: dnsmasq, FQDN, TTL and CNAME.
- CNAME uses the second row of its between-card connector, spanning its full width. The arrow remains centered in the first row.
- Align the note toward the word within that row, clamping it to the row edges. Rendered coordinates are converted once to local CSS pixels for zoom.
- Remove the fixed top/right docks. The definition remains in normal flow before hydration and without geometry measurement. Horizontal measurement only improves alignment; it never overlays content.
- Retain complete text, accessible description association, motion/forced-color support and collision-safe decorative leaders.

## Verification

Local production build, TypeScript and content checks pass. Thirteen pure geometry/flow tests pass. The browser suite now checks local adjacency, bounded gap, note and text containment, no covered controls/cards/arrows, unique accessible IDs, CNAME connector alignment and scenario switching at six viewport sizes including 320px, plus 125%/200% zoom. Full browser results are tracked on the exact published commit rather than inferred from unit tests.

The supplied screenshot was only 41×41px, so the exact original callout could not be identified from it. The correction covers all four shared callout placements rather than guessing a specific term.
