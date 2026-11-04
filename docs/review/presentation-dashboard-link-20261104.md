# Presentation dashboard link

The presentation header now includes a native same-origin `/dashboard` link labeled 대시보드. It follows the existing Vercel control-service rewrite rather than Next client routing. Enter, modifier-click and browser Back retain native link behavior; Back returns to the presentation fragment. No account, session or policy action is performed by rendering the link.

The chapter region may shrink without pushing actions outside the header. Mobile action groups wrap when the optional microphone-stop action makes them wider; the existing content-driven header height reserves the additional row.

The browser test checks five viewport widths including 320px, 200% CSS zoom, optional microphone layout, no overlapping/clipped header labels, Enter navigation and Back to slide9. Its dashboard response is an explicit local fixture because the Next-only test server does not run Vercel rewrites. It does not assert dashboard authentication or live backend availability.
