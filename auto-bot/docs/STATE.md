# AutoBot — Project State as of June 25, 2026

## What is live on main / Render

- `/health` — basic health check
- `/fb/extract_html` — GPT-4o field + image extraction (core scraper)
- `/auth/register` — bcrypt hash + Supabase insert + JWT response
- `/auth/login` — bcrypt verify + JWT response
- `/auth/verify` — JWT decode + return {email, tier}

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
