# 2026-07-13 — Extension install button wired to Chrome Web Store

## Orient

- Branch: `main`, up to date with `origin/main`. Last commit before this session:
  `661cab8 feat(scrub): Standard-tier watermark scrub via gpt-4o + gpt-image-1.5`. Working tree was clean
  aside from an unrelated stale `.pyc` and an untracked `CLAUDE.md`.
- `PROJECT_BRIEF.md` does not exist anywhere in the repo (searched the full tree). Per user decision, updated
  `docs/STATE.md` instead — see that file's new note.
- Post-sign-in / authenticated view: `website/account.html`. Guarded by a hard redirect to `login.html` when
  no `postbot_token` is in `localStorage` (lines ~481-485).
- A "Chrome Extension" card already existed there (`#extensionCard`), with a `Download Extension` anchor
  (`#extensionBtn`) that had `href="#"` and an explicit placeholder comment:
  `EXTENSION LINK SLOT — replace href="#" with Chrome Web Store URL when published`. The card itself is
  additionally gated on `tier === 'standard'` (existing JS, untouched).

## Change

`website/account.html` — wired the `#extensionBtn` anchor to
`https://chromewebstore.google.com/detail/marketfill/fglemlgblmefkgdaggaldadkmciabdnl`, added
`target="_blank" rel="noopener noreferrer"`, removed the now-stale placeholder comment, and updated the
helper text from "Chrome Web Store link coming soon" to "Opens the Chrome Web Store in a new tab". No auth
logic, routing, or anything else on the page was touched.

## Out of scope / flagged, not changed

`website/success.html` (post-checkout landing page) has the same dangling `href="#"` install button, but
unlike `account.html` it is **not** auth-gated — it renders unconditionally regardless of sign-in state.
Wiring the URL there without adding conditional auth-gating would violate "never on the signed-out screen";
adding that gating would mean touching auth-state logic, which the task explicitly said to flag and stop on.
Left untouched. Noted in `docs/STATE.md` as a follow-up.

## Verify

- (1) Signed out: confirmed via code — `account.html` redirects unauthenticated visitors straight to
  `login.html` before any card (including the extension button) is ever rendered.
- (2) and (3) — sign-in flow and live button check — require a real login, which needs a password to be
  entered. Per the assistant's operating constraints, credential entry isn't something it performs even when
  supplied, so this was not exercised live. **User opted to verify this step themselves** (chose "I'll verify
  it myself" when asked). Pending confirmation from user that:
  - Signed out → button not visible
  - Signed in → button appears, links to the exact Chrome Web Store URL, opens in a new tab
  - Sign-in flow itself still works normally
