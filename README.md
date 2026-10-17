# Legacis81 read-only Etsy authorization handoff

GitHub Pages hosts only the PKCE authorization and callback validation UI. It does not call Etsy's token endpoint, hold a GitHub credential, or receive OAuth access/refresh tokens. A restrictive CSP disallows browser API connections. Use the same Android browser tab for start and callback.

Before starting, merge and configure the matching secure-storage workflow in the PRIVATE `legacis81-price-manager` repository, then run its `preflight` operation successfully. Keep the exact Etsy registered redirect URI: https://legacis81-cloud.github.io/legacis81-etsy-callback/

After Etsy consent, state, duplicate parameters and a 15-minute local session deadline are checked. The callback removes sensitive query parameters from browser history and consumes session state once. Copy the temporary code/verifier package directly into the PRIVATE Actions secret `ETSY_OAUTH_HANDOFF` and immediately run the private workflow with `exchange`. Never paste it in chat, workflow inputs, issues, source code or screenshots. No tokens are displayed here. The package clears at session expiry or when you press Clear; clear the Android clipboard afterwards.

The manual handoff uses GitHub's existing secret editor and avoids hosting a backend or exposing a GitHub credential in public JavaScript. It is not a fully automatic OAuth service. If the code expires, start again; do not repeatedly retry a consumed code. See the private repository README for storage setup, refresh rotation, permissions and recovery limitations.

Tests: `node --test tests/*.test.cjs` (no credentials or external requests).
