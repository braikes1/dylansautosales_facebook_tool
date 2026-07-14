# AutoBot — Project State as of July 13, 2026

Note: task instructions in this repo have referenced a `PROJECT_BRIEF.md` file, but no such file exists
anywhere in the repo (checked full tree). This file (`docs/STATE.md`) is the actual running log per
`CLAUDE.md`; update it going forward instead of a `PROJECT_BRIEF.md`.

## What is live on main / Render

- `/health` — basic health check
- `/fb/extract_html` — GPT-4o field + image extraction (core scraper)
- `/fb/scrape_url` — FireCrawl-based structured extraction (primary detail-enrichment path)
- `/fb/scrub_image` — Standard-tier watermark removal (gpt-4o detection + gpt-image-1.5 edit), JWT + tier gated
- `/auth/register` — bcrypt hash + Supabase insert + JWT response
- `/auth/login` — bcrypt verify + JWT response
- `/auth/verify` — JWT decode + return {email, tier}
- `/billing/create-checkout`, `/billing/portal`, `/billing/webhook` — Stripe subscription flow

## Website

- `website/account.html` — post-sign-in account view (hard auth redirect to `login.html` if no token).
  "Chrome Extension" card (`#extensionCard`) is visible only for `tier === 'standard'` and now links to the
  published Chrome Web Store listing (`#extensionBtn`, opens in a new tab). Previously a `href="#"` placeholder.
- `website/success.html` — post-checkout landing page. Has its own `#extensionBtn` with the same unwired
  `href="#"` placeholder, but the button is **not** gated by auth state at all (renders regardless of token
  presence) — fixing it the same way would either leave it visible to signed-out visitors or require adding
  auth-gating logic to the page, which is out of scope for a button-only change. Left untouched; flagged here
  as a follow-up.

## Supabase

Custom `users` table (NOT Supabase Auth):
- id, email, password_hash, tier, stripe_customer_id, created_at

## Render env vars required (web service)

- OPENAI_API_KEY
- SUPABASE_URL
- SUPABASE_SERVICE_KEY
- JWT_SECRET

## Stripe

Sandbox mode. Price ID: `price_1TlzXPRvbsBXVbcqerMgexrZ`

## Next features (in order)

1. `feature/stripe-billing` — checkout + webhook, flip tier on payment
2. `feature/auth-gate` — login screen in extension, JWT stored, validated before scrape
3. Tier check in scraper — paid=full, unpaid=blocked
4. Distribution — WordPress landing page, Chrome Web Store submission
