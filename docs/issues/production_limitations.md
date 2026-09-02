# DukaanDar — Production Limitations Before Beta Launch

> **What this is:** a plain-language list of everything found in the code that can hurt you
> once 10 real shopkeepers start using the app for real money and real customers.
> Every item has: what it is, what will actually happen (scenario), and how serious it is.
>
> **Reviewed:** 2026-08-19 · branch `hotfix/billing-dashboard`
> **Scope:** `node-backend` (gateway, auth-service, core-service), `flutter-frontend`, database migrations, Fly.io deploy config.
>
> **Status (2026-08-20): all CRITICAL, all HIGH, and all MEDIUM issues are addressed.**
> Three are deliberately partial or declined, each explained in its own entry:
> **C-6** (registration left open, product owner's call), **M-9** (offline mode — a feature, not a
> fix), **M-1 / M-10 / M-11** (the remaining parts need Redis, monitoring accounts, or an auth layer
> the dashboard does not have).
>
> Backend verified by `npm test` — **434 tests passing** (was 245 before any of this work),
> build, typecheck, `flutter analyze` and the dashboard typecheck all clean.
> Frontend changes compile but are **not manually exercised** — they need a run on a device.
>
> ⚠ **H-8 was previously reported fixed and was not** — see its entry. Corrected in migration 028.
>
> **Ten migrations (019–028) and several env vars must be applied.**
> See "Deploying these fixes" at the bottom, and `node-backend/docs/operations-runbook.md`.

---

## How to read the severity

| Level | Meaning | When to fix |
|---|---|---|
| **CRITICAL** | Money, data or accounts can be lost or stolen. Beta will visibly break. | **Before launch. Do not ship without these.** |
| **HIGH** | Real damage is likely during the beta, or a bad person can abuse it easily. | Before launch if possible, otherwise in week 1. |
| **MEDIUM** | Will cause confusion, wrong numbers or support calls. | During the beta. |
| **LOW** | Hygiene, cost and polish. | After the beta. |

---

# CRITICAL

## C-1 — Staff passwords are saved in plain text and sent back to the app

**STATUS: FIXED** — `plain_password` is no longer written or read anywhere; every users query
now selects an explicit safe column list instead of `*`. Column dropped by migration
`019_drop_plain_password.sql`. Client no longer models or pre-fills the password.
Covered by tests in `user.service.test.ts` ("does not persist the password", "never selects the password column").
⚠ Treat every password ever stored there as compromised — see the migration header.

**Where:** [user.service.ts:100](node-backend/services/core-service/src/services/user.service.ts#L100), [user.service.ts:189](node-backend/services/core-service/src/services/user.service.ts#L189), [009_add_plain_password_to_users.sql](node-backend/docs/db/supabase/migrations/009_add_plain_password_to_users.sql), [staff_model.dart:39](flutter-frontend/lib/Models/user/staff_model.dart#L39)

When a shop owner creates a salesman account, the raw password is written into the
`users.plain_password` column. `listStaff()` then does `select('*')`, so that plain
password travels over the network and lands inside the Flutter app, where the staff
edit screen fills it into the password box.

**Scenario:** One shopkeeper reuses his personal Gmail password for his salesman login.
That password now sits readable in your database, in your API responses, and in your
server logs if anything ever dumps a response body. If your Supabase project, a backup,
or one laptop is compromised, you have handed over every shopkeeper's real password —
and because people reuse passwords, their bank and email go with it. This is also a
straight legal/PII problem, not just a technical one.

**Level:** CRITICAL

**Fix:** Drop the `plain_password` column, remove it from the insert/update in
`user.service.ts`, and stop `select('*')` on the users table. If owners need to hand a
password to staff, show it once at creation time and never store it.

---

## C-2 — Any logged-in user can read and edit any user of any shop

**STATUS: FIXED** — `getByEmail`, `getById` and `update` all take a shop id and filter on it.
Non-admins may only touch their own row; admins are still confined to their own shop.
Covered by tests asserting `shop_id` filtering on every path, plus a test that a profile
update cannot smuggle in a `role` change.

**Where:** [user.routes.ts:54-66](node-backend/services/core-service/src/routes/user.routes.ts#L54-L66), [user.service.ts:21-55](node-backend/services/core-service/src/services/user.service.ts#L21-L55)

These three routes have no shop check and no role check — only `requireAuth`:

- `GET /api/v1/users?email=...` → returns the full row (`select('*')`) for **any** email
- `GET /api/v1/users/:id` → returns the full row for **any** user id, any shop
- `PUT /api/v1/users/:id` → edits name, email, phone, DOB of **any** user, any shop

Every other route in the service correctly uses `getShopId(req)`; these were missed.

**Scenario:** Shopkeeper A's salesman (lowest role, `viewer` permissions) opens the app,
and simply walks the ids: `GET /api/v1/users/1`, `/2`, `/3`… He now has the names,
emails, phone numbers **and plain-text passwords (C-1)** of every owner and every staff
member of the other 9 beta shops. With `PUT /api/v1/users/7` he can change a rival
owner's email address in the profile table. Combined with C-1 he can then log into
their shop and see their whole business.

**Level:** CRITICAL

**Fix:** Scope all three to `getShopId(req)` (and require `admin` for lookups by
email/id), and return an explicit whitelist of columns instead of `*`.

---

## C-3 — Core-service believes whatever identity headers it is given

**STATUS: FIXED** — three layers:
1. the gateway strips any client-supplied `X-User-*` / `X-Shop-Id` / signature header on the way in;
2. it signs every proxied request with `GATEWAY_SHARED_SECRET`;
3. core-service **and** auth-service reject anything unsigned, before any identity header is read.
The published ports are gone from both `fly.toml` files and from `docker-compose.yml`, so the
services are private-network only. Covered by 14 tests in `packages/middleware/tests/gatewayTrust.test.ts`,
including the exact attack (identity headers, no signature), prefix guesses and duplicate-header smuggling.
⚠ If these apps still hold a public IP from an earlier deploy, release it — see the fly.toml comments.

**Where:** [auth.middleware.ts:136-149](node-backend/packages/middleware/src/auth.middleware.ts#L136-L149), [core-service/src/app.ts:60](node-backend/services/core-service/src/app.ts#L60), [core-service/fly.toml](node-backend/services/core-service/fly.toml)

The gateway checks the JWT and then injects `X-User-Id`, `X-User-Role`, `X-Shop-Id`,
`X-User-Permissions` as "trusted internal headers". Core-service simply reads those
headers and treats them as the logged-in user. There is **no shared secret, no mTLS, no
signature, and no check that the request actually came from the gateway.**

Meanwhile `core-service/fly.toml` declares a `[[services]]` block publishing port 3002.
The moment that app has any public IP (Fly assigns shared IPv4 easily, and a single
`fly ips allocate` does it), port 3002 answers the open internet.

**Scenario:** Someone finds `dukaandar-core-service.fly.dev:3002` (or gets any code
running inside your Fly organisation network). They send:

```
GET /api/v1/reports/sales
X-User-Id: x
X-User-Email: x@x.com
X-User-Role: admin
X-Shop-Id: 4
```

No token, no password. They now read, edit and delete shop 4's products, customers,
orders and khata — and can loop `X-Shop-Id` from 1 to 100 to dump every shop in the
system. This one bypasses your entire login system.

**Level:** CRITICAL

**Fix:** (a) Remove the public `[[services]]`/ports block from core-service and
auth-service so they are private-network only, and (b) add a `GATEWAY_SHARED_SECRET`
header that core-service verifies on every request, rejecting anything without it. Do
both — (b) is what protects you when someone gets inside the network.

---

## C-4 — Every new shop starts with 0 credits, so the app is blocked before the shopkeeper can top up

**STATUS: FIXED** — new shops are granted `SIGNUP_CREDIT_GRANT` (default 500) at registration,
written through the ledger so it is auditable. Migration `020_signup_credit_grant.sql` sets the
column default and backfills existing empty shops. `POST /api/v1/billing/grant` now lets you
fulfil a WhatsApp top-up with one call instead of hand-written SQL; it is guarded by
`INTERNAL_ADMIN_KEY` and fails shut when that key is unset.
Covered by `billing.grant.test.ts` (including the sign of the ledger entry — a grant must be a
NEGATIVE deduction, or it would drain the shop) and `grantGuard.test.ts`.

**Where:** [016_billing_membership_credits.sql:11](node-backend/docs/db/supabase/migrations/016_billing_membership_credits.sql#L11) (`credits_balance numeric NOT NULL DEFAULT 0`), [supabase-auth.service.ts:314](node-backend/services/auth-service/src/services/supabase-auth.service.ts#L314) (`provisionShop` never sets credits), [creditDeduction.middleware.ts:17-21](node-backend/services/core-service/src/middlewares/creditDeduction.middleware.ts#L17-L21) (`NODE_ENV=production` → billing always enforced), [billing.routes.ts](node-backend/services/core-service/src/routes/billing.routes.ts) (read-only: summary, ledger, usage, tiers)

Billing cannot be switched off in production — `isDevUnlimitedCredits()` returns `false`
whenever `NODE_ENV=production`. New shops are created with a balance of `0`, and nothing
grants a starting balance at signup.

Topping up is a **deliberately manual WhatsApp flow**
([TopUpTab.tsx](dashboard/components/dashboard/TopUpTab.tsx): "No card form, and there
will not be one — billing is prepaid credit bought over WhatsApp"), which is a valid
choice for a 10-shop beta. The problem is the two ends of it: the shop is blocked from
the first minute, and on your side there is **no endpoint or script that actually credits
a shop** — so you fulfil every WhatsApp request by hand-writing SQL in the Supabase
console.

**Scenario:** Day 1 of the beta. A shopkeeper registers, adds his first product… and gets
`402 Insufficient credits`. Every write in the app is blocked before he has any reason to
know a WhatsApp top-up exists — his first experience of your product is that it doesn't
work. He messages you; you open Supabase and type an `UPDATE` by hand. Repeat ten times
on launch morning, then again every time a shop runs dry (a POS sale costs 15 credits, a
report 75) — including at 9 p.m. on a Sunday, while that shop cannot sell.

**Level:** CRITICAL — the day-1 block is a certainty, not a risk.

**Fix:** Two things. (1) Grant a starting balance so a new shop can work immediately —
set it in `provisionShop` (and as the column default), or put beta shops on a
`membership_plan` that skips deduction. (2) Add an internal credit-grant endpoint
(service-role only, with a ledger entry so the top-up is auditable) so fulfilling a
WhatsApp request is one authenticated call instead of hand-written SQL. Also add a
low-balance warning in the app before it hits zero — `shop_controller.dart` already
tracks `lowCreditThreshold`, so the signal exists.

---

## C-5 — A retried sale creates a second sale and deducts stock twice

**STATUS: FIXED** — the app now generates one UUID per sale, reuses it across retries, and clears
it only once the sale commits or the cart is cleared. The server **requires** the key, so an
unprotected checkout is no longer possible. The remaining race (two identical checkouts passing
the RPC's idempotency SELECT together) is resolved by catching the unique violation and returning
the winner's order as a duplicate, instead of a 500. Checkout timeout raised 15s → 40s to stop
cold starts producing the timeout in the first place.
Covered by `checkout.service.test.ts` (duplicate-protection block) and `posCheckoutSchema.test.ts`.
⚠ **Deploy the backend and the app together** — the required key means an old client cannot check out.

**Where:** [order_repository.dart:262](flutter-frontend/lib/repositories/order/order_repository.dart#L262), [order_item_model.dart:172-194](flutter-frontend/lib/Models/orders/order_item_model.dart#L172-L194) (`OrderModel.toJson`), [backend_api_service.dart:55](flutter-frontend/lib/services/backend/backend_api_service.dart#L55) (15s timeout), [018_atomic_pos_checkout.sql:84](node-backend/docs/db/supabase/migrations/018_atomic_pos_checkout.sql#L84)

The database has proper duplicate protection — but only if the app sends an
`idempotencyKey`. The app reads `orderJson['idempotency_key']`… and `OrderModel.toJson()`
never produces that field. **No checkout in the app ever sends an idempotency key.**
On top of that the HTTP timeout is 15 seconds while the backend runs with
`min_machines_running = 0` (cold start).

**Scenario:** Evening rush. The cashier hits "Checkout" on a Rs. 4,500 bill. The Fly
machine was asleep, so the request takes 16 seconds — the app gives up at 15 and shows
"Failed to create order. Please try again." The sale actually **did** commit on the
server. The cashier presses Checkout again. Result: two orders for one basket, stock
deducted twice, the customer's khata debited twice, and the day's sales report
overstated. The shopkeeper loses trust in the numbers immediately — and inventory drifts
from reality permanently.

**Level:** CRITICAL

**Fix:** Generate a UUID per checkout attempt in `sales_controller`, keep it stable
across retries, put it in the payload, and raise the client timeout for
`/pos/checkout` (30-40s). Also see M-4 about the unique index being global.

---

## C-6 — Registration is completely open to the internet

**STATUS: BY DESIGN — not fixed, reverted on request.** An allowlist/access-key gate was built and
then removed at the product owner's explicit direction: this app is meant to be open to any email
for the beta, and the admin-key mechanism is legacy that was already being phased out
(`017_remove_admin_key_logic.sql` had already dropped the `extras` table it used to check against).
`verify-admin-key` is now a permanent no-op kept only so the existing signup screen call keeps
working; `adminKey` has been removed from the request DTOs and validators entirely.

This is a deliberate tradeoff, not an oversight — flagging it here so it isn't silently reintroduced
later: with registration open, anyone who has the API URL can create shops. For a 10-shopkeeper beta
where you know who is testing, the operational cost of a closed gate (coordinating an allowlist,
handling access-key distribution) was judged not worth it. If abuse becomes a problem, the fastest
mitigation is tightening `authRateLimiter` on the registration routes rather than reintroducing a
gate; a member of Scrutinize can re-add the allowlist approach on request — it existed once and can
be restored the same way.

**Where:** [auth.controller.ts:19-21](node-backend/services/auth-service/src/controllers/auth.controller.ts#L19-L21), [supabase-auth.service.ts:31-33](node-backend/services/auth-service/src/services/supabase-auth.service.ts#L31-L33), [017_remove_admin_key_logic.sql](node-backend/docs/db/supabase/migrations/017_remove_admin_key_logic.sql)

`verifyAdminKey` is a stub that returns `{ valid: true }` unconditionally, and the
`extras` table it used to check was dropped. The signup gate exists in the UI but
enforces nothing. Anyone with the API URL can create accounts and shops.

**Scenario:** Your API URL leaks (it is in a committed `.env`, see H-2). A bot signs up
2,000 shops overnight. Each signup sends a real email through Resend, calls
`auth.admin.listUsers()` (see M-2 — this gets slower with every user), and creates rows
in `shop` and `users`. Your Supabase and Resend quotas are burned, your 10 real
shopkeepers cannot register or log in, and you cannot tell real from fake in your own
dashboard.

**Level:** CRITICAL for a 10-user closed beta (you want a closed door, and there isn't one).

**Fix:** For the beta, gate registration properly — either restore a server-side invite
code checked against a table, or pre-create the 10 accounts yourself and disable the
public register/OTP routes at the gateway.

---

# HIGH

## H-1 — The customer's outstanding (udhaar) amount is calculated wrong

**STATUS: FIXED** (migration `023`) — the khata is now recorded against the real payable
total instead of `sub_total`.

⚠ **The fix in this document's original write-up was wrong for this codebase.** It proposed
`sub_total - discount + tax + extra_amount`. Reading `sales_controller.dart` shows the client
already subtracts the discount before sending (`subTotal = originalSubTotal - discountAmount`),
so subtracting it again would have understated the debt a second time. It also omitted the
salesman commission, which the app *does* include in the bill total.

The formula actually implemented mirrors `calculateNetTotal()`:
`payable = sub_total + tax + extra_amount + commission`, where
`commission = round(percent * sub_total / 100, 2)`.

Two related bugs were fixed on the way: the commission was never persisted (the old RPC wrote a
hard-coded `0`), and the percent was never sent by the client at all — both now flow through.
Covered by `checkoutPayable.test.ts` (9 tests, including "does not subtract discount a second time").


**Where:** [018_atomic_pos_checkout.sql:201-209](node-backend/docs/db/supabase/migrations/018_atomic_pos_checkout.sql#L201-L209)

The khata entry is written as `v_sub_total - v_paid_amount`. `sub_total` is product
prices only — the frontend comment says so explicitly. Tax, discount, extra charges and
delivery are all ignored, even though the order row stores them.

**Scenario:** Bill = Rs. 10,000 goods + Rs. 500 tax + Rs. 200 extra − Rs. 300 discount
= Rs. 10,400 due. Customer pays Rs. 5,000. The app records the debt as Rs. 5,000
instead of Rs. 5,400. Every partly-paid credit sale is off. Over a month of khata
selling, the shopkeeper is quietly short thousands of rupees and the account book never
reconciles. For a karyana app whose whole value is the khata, this destroys trust.

**Level:** HIGH

**Fix:** Compute the payable total inside the RPC
(`sub_total - discount + tax + extra_amount`) and use that for both the account-book
entry and the "is it fully paid" check. Add a test that a partly-paid taxed sale
produces the exact outstanding amount.

---

## H-2 — Secrets are committed to git and shipped inside the app

**STATUS: FIXED in code — ⚠ KEY ROTATION IS STILL ON YOU.**
`flutter-frontend/.env` is untracked (`git rm --cached`; the local file is untouched) and the root
`.gitignore` now blocks `.env`/`*.env` while keeping `*.env.example`. No AI key ships in the APK
any more: the client (now `AiDescriptionService`) calls `POST /api/v1/products/ai/description`, and
the key lives only in core-service. The provider was switched from Gemini to **OpenAI
`gpt-4o-mini`** at the same time — `OPENAI_API_KEY` / `OPENAI_MODEL`, server-side only, so changing
model or provider later needs no app release. The dormant service-role key path is deleted
outright from `secure_keys.dart` and `supabase_strings.dart` — nothing in the client reads a
service key any more.

Covered by 11 tests in `ai.service.test.ts`, including that the key goes in an `Authorization`
header (never the URL, where the old client put it) and that an upstream auth error — which echoes
the key back — is never forwarded to the shopkeeper.

⚠ **Still required from you:** the old Gemini key and the Supabase anon key were in git history, so
both must be treated as leaked. The Gemini key is no longer used at all and should simply be
**revoked**; the Supabase anon key still needs **rotating**. Untracking a file does not remove it
from past commits.


**Where:** [flutter-frontend/.env](flutter-frontend/.env) (tracked in git), [.gitignore](.gitignore) (does not ignore `.env`), [gemini_service.dart:7](flutter-frontend/lib/utils/ai/gemini_service.dart#L7), [secure_keys.dart:38-41](flutter-frontend/lib/utils/security/secure_keys.dart#L38-L41)

`flutter-frontend/.env` is checked into the repository and contains the live
`GEMINI_API_KEY`, the Supabase project URL and anon key. The root `.gitignore` only
excludes two unrelated paths, so nothing stops the next `.env` from being committed too.
`GeminiService` calls Google directly from the phone with that key in the URL — meaning
the key is inside every APK you hand out. `SecureKeys.supabaseServiceKey` still has a
code path that would read a **service-role** key from the same client `.env` (currently
commented out, so dormant — but one uncomment away from a total breach).

**Scenario:** You share the repo with a contractor, or push it public, or one beta tester
unzips the APK. Your Gemini key is now someone else's free AI quota — they run it flat
out and Google bills you, or rate-limits you so "generate description" stops working for
your shopkeepers. If the service-key line is ever re-enabled, whoever has the APK owns
your entire database with RLS bypassed.

**Level:** HIGH

**Fix:** `git rm --cached flutter-frontend/.env`, add `.env` to `.gitignore`, **rotate
the Gemini key and the Supabase anon key** (they must be treated as leaked), move Gemini
calls behind the backend so the key never ships, and delete the service-key code path
from `secure_keys.dart` / `supabase_strings.dart`.

---

## H-3 — A shop owner can promote someone to `super_admin` and see every shop

**Where:** [user.service.ts:70-83](node-backend/services/core-service/src/services/user.service.ts#L70-L83), [user.service.ts:169-172](node-backend/services/core-service/src/services/user.service.ts#L169-L172), [002_enable_row_level_security.sql:40-72](node-backend/docs/db/supabase/migrations/002_enable_row_level_security.sql#L40-L72)

`createStaff` and `updateStaff` copy `role` and `permissions` straight from the request
body into Supabase `app_metadata`. Nothing validates that the value is one of the
allowed staff roles. The database's own RLS says `is_super_admin()` sees **all shops**.

**Scenario:** A beta shopkeeper (or his tech-savvy nephew) opens the staff screen, edits
the network request, and creates a staff account with `"role": "super_admin"`. That
account's JWT now carries `super_admin`, so `belongs_to_shop()` returns true for every
shop, `requireRole('admin','super_admin')` passes everywhere, and he can read the other
9 shops' sales, prices and customers.

**Level:** HIGH

**Fix:** Whitelist the accepted values server-side (`admin`, `salesman`, `viewer` only —
never `super_admin` from an API call) and whitelist the permission strings too.

---

## H-4 — In production, the app hides the real reason a checkout failed

**STATUS: FIXED** — the `if (kDebugMode)` guards around the checkout error snackbars are gone, so
release builds show the reason. Failures now carry the backend's error code via a new
`CheckoutFailedException`, and the cashier gets an actionable message: "Credits Finished",
"Not Enough Stock", or — for the timed-out-but-maybe-saved case — "Sale May Already Be Saved:
check the Orders list before ringing it up again". The controller's generic
"Failed to create order. Please try again." was removed so it cannot bury the specific message.


**Where:** [order_repository.dart:157-161](flutter-frontend/lib/repositories/order/order_repository.dart#L157-L161), [order_repository.dart:220-226](flutter-frontend/lib/repositories/order/order_repository.dart#L220-L226)

The error snackbars in the checkout paths are wrapped in `if (kDebugMode)`. In a release
build `kDebugMode` is `false`, so those messages never appear; the function just returns
`orderId: -1`. The caller shows one generic line: "Failed to create order. Please try
again."

**Scenario:** A sale fails because one item is out of stock ("Insufficient stock for
Sugar 1kg. Available: 2, requested: 5") — or because credits ran out (C-4), or because
the queued-checkout poll timed out with the sale possibly still processing. The cashier
sees only "Failed to create order. Please try again", so she tries again. And again.
She cannot fix the actual problem, the queue behind her grows, and your support phone
rings with "the app just says failed". For the timed-out-but-processing case, retrying
is exactly the wrong action (see C-5).

**Level:** HIGH

**Fix:** Remove the `kDebugMode` guards around user-facing error snackbars and pass the
backend's `errorMessage`/`errorCode` up to the checkout screen. Handle `402` and the
`CheckoutPendingException` with their own clear messages ("Credits finished — contact
support" / "Sale may already be saved — check Orders before retrying").

---

## H-5 — Staff can be logged out at random during a shift

**STATUS: FIXED** — the `bool _isRefreshing` flag is replaced by a shared `Future<bool>?`. Requests
that hit a 401 while a refresh is running now await that same future and receive its real outcome,
instead of being told it failed and force-logging-out the user. This is the subscriber-queue
pattern already used by the Next.js dashboard, as the original write-up suggested.


**Where:** [backend_api_service.dart:64](flutter-frontend/lib/services/backend/backend_api_service.dart#L64), [backend_api_service.dart:93-96](flutter-frontend/lib/services/backend/backend_api_service.dart#L93-L96)

`_tryRefreshToken()` has a simple `_isRefreshing` flag: if a refresh is already in
progress, it returns `false` — and `false` means "refresh failed", which triggers
`_forceSessionEviction()` and kicks the user out.

**Scenario:** The dashboard loads products, customers, orders and billing at the same
time. The access token has just expired, so four requests come back `401` together. The
first one refreshes successfully; the other three see `_isRefreshing == true`, get
`false`, and force a logout. The shopkeeper is thrown to the login screen mid-sale, with
a half-built cart lost. It looks random, so it is very hard for you to reproduce from a
bug report.

**Level:** HIGH

**Fix:** Share one refresh `Future` — callers arriving while a refresh is in flight
should await that same future and get its real result, instead of being told it failed.
**The correct version already exists in this repo:** the Next.js dashboard solves exactly
this with a subscriber queue in
[dashboard/lib/api.ts:44-51](dashboard/lib/api.ts#L44-L51) (`subscribeTokenRefresh` /
`onRefreshed`). Port that pattern to `backend_api_service.dart`.

---

## H-6 — Checkout never checks that the customer / salesman belongs to the shop

**STATUS: FIXED** (migration `023`) — `pos_checkout_atomic` now validates `customerId`,
`salesmanId` and `userId` against `p_shop_id` before creating anything, raising
`CHECKOUT_NOT_FOUND` on a mismatch. Shipped in the same migration as H-1 because both live inside
that function.


**Where:** [018_atomic_pos_checkout.sql:98](node-backend/docs/db/supabase/migrations/018_atomic_pos_checkout.sql#L98), [018_atomic_pos_checkout.sql:162-183](node-backend/docs/db/supabase/migrations/018_atomic_pos_checkout.sql#L162-L183)

Stock rows are correctly filtered by `shop_id`, but `customerId`, `salesmanId` and
`userId` are inserted straight from the request with no ownership check.

**Scenario:** A user posts a checkout with a `customerId` belonging to another shop. The
order and the khata entry are written into his own shop but point at a stranger's
customer row. His customer list, ledger and installment screens now show entries that
resolve to a name he does not have — or blank/broken rows — and the other shop's customer
appears in reports that were never his. Cleaning this up later means hand-fixing rows.

**Level:** HIGH

**Fix:** Inside the RPC, validate each of `customerId`, `salesmanId`, `userId` against
the same `p_shop_id` and raise `CHECKOUT_NOT_FOUND` if they don't match.

---

## H-7 — Weak passwords and no protection against password guessing

**STATUS: FIXED** (migration `024`) — two parts.

*Password policy*: a shared `assertStrongPassword` in `@dukaandar/shared` requires 10+ characters,
a letter plus a digit or symbol, and rejects common/sequential/repeated passwords. Enforced
wherever a password is **set** — registration and staff create/update. Deliberately **not**
enforced at login, so existing accounts with short passwords can still sign in. 22 tests.

*Lockout*: a `login_attempts` table keyed by a **hash** of the email (so the table never becomes a
directory of your users) counts failures atomically in one statement. 8 failures inside 15 minutes
locks the account for 15 minutes; a successful login clears the counter. Being in the database
rather than in memory means it survives scale-to-zero and is shared across machines — the exact
gap the original write-up flagged. The lockout store fails **open** if it errors, so a database
hiccup cannot lock everyone out of their own shops.


**Where:** [auth.validator.ts:5](node-backend/services/auth-service/src/validators/auth.validator.ts#L5) (min 6 chars), [rateLimiter.middleware.ts:6-13](node-backend/packages/middleware/src/rateLimiter.middleware.ts#L6-L13)

Passwords need only 6 characters, with no other rule. Login protection is a per-IP
limiter (20 requests / 15 min) held **in memory** — there is no per-account lockout and
no notification on repeated failures.

**Scenario:** A shopkeeper picks `123456`. A former employee who knows the owner's email
tries the twenty most common PIN-style passwords from his phone, waits fifteen minutes,
switches to mobile data for a fresh IP, and repeats. Nothing locks, nothing alerts. Once
in, he has the owner's full admin account: prices, khata, staff, reports.

**Level:** HIGH

**Fix:** Require 10+ characters and reject the obvious ones. Add per-email failed-login
counting with a temporary lock, and move the rate-limit store to the Redis you already
run (see M-1).

---

## H-8 — Removing a staff member's permissions doesn't take effect immediately

**STATUS: NOW ACTUALLY FIXED** (migration `028`) — ⚠ **it was previously reported as fixed and was
not.**

The earlier fix called `auth.admin.signOut(authUid)`. That API takes a **JWT, not a user id**, so it
never revoked anything — and because the error was swallowed (`.catch(() => null)`) it looked like it
worked. An owner who stripped a salesman's permissions was told access was cut when it was not. This
surfaced while doing M-11, which uses the same API.

The admin never holds the staff member's JWT, so revocation has to happen in the database:
`fn_revoke_user_sessions` deletes their `auth.sessions` and `auth.refresh_tokens` rows. A failure is
now logged loudly instead of swallowed.

**Honest limitation:** this is not instant. A Supabase access token is a signed JWT and cannot be
recalled without a per-request denylist this system does not have, so a revoked user keeps working
until their current access token expires (~1 hour), then cannot refresh. That is the difference
between "access ends within the hour" and "the session refreshes forever", which is what was
happening. For an immediate cut-off, delete the staff account — that path works today.


**Where:** [rbac.middleware.ts:45-65](node-backend/packages/middleware/src/rbac.middleware.ts#L45-L65), [auth.middleware.ts:37-48](node-backend/packages/middleware/src/auth.middleware.ts#L37-L48)

Roles and permissions are read out of the JWT, and the JWT is only rebuilt when the token
refreshes. `updateStaff` changes `app_metadata` but does not revoke existing sessions.

**Scenario:** An owner catches a salesman fiddling with prices and immediately strips his
`pos_sale` and `manage_account_book` permissions. The salesman's phone still holds a
valid token with the old permissions, so he keeps selling and editing the khata until
that token expires. The owner believes he cut access; he did not.

**Level:** HIGH

**Fix:** Sign out the user's sessions (`auth.admin.signOut`) whenever role or permissions
change, or check the sensitive permissions against the `users` table row instead of the
token.

---

# MEDIUM

## M-1 — Rate limits reset every time a machine sleeps, and aren't shared

**STATUS: PARTIALLY FIXED — one half needs infrastructure you must provision.**

*Fixed:* `skipSuccessfulRequests: true` is gone. Successful requests were not counted at all, so
there was effectively **no ceiling** on a client that kept succeeding — and now that billing charges
up front (M-5) a runaway loop spends the shopkeeper's credits. Every request is counted, with the
general limiter at 240/min: far above a real screen load (~30 requests) and far below a loop.
6 behavioural tests drive real traffic through the limiter.

*Not fixed:* the counters are still in memory. A shared store needs **Redis, which does not exist in
production** — docker-compose has one for local dev and nothing reads `REDIS_URL`. Provisioning that
is your call, so `setRateLimitStore()` is exported and the limiter takes a store: wiring
`rate-limit-redis` later is a few lines, not a rewrite.

Two things blunt the gap meanwhile: the gateway now keeps a machine warm (M-6) so counters stop
resetting constantly, and brute force against a specific account is stopped by the database-backed
lockout from H-7, which does survive restarts and is shared across machines.


**Where:** [rateLimiter.middleware.ts](node-backend/packages/middleware/src/rateLimiter.middleware.ts), [gateway fly.toml](node-backend/gateway/api-gateway/fly.toml) (`min_machines_running = 0`), [api-gateway/src/app.ts:41](node-backend/gateway/api-gateway/src/app.ts#L41)

`express-rate-limit` is used with its default in-memory store, and the general limiter
sets `skipSuccessfulRequests: true` — so successful requests are not counted at all.
With scale-to-zero and multiple machines, each machine keeps its own counters and loses
them on every restart.

**Scenario:** Someone hammering the login endpoint just waits for the machine to scale
down, or spreads requests across machines, and the counter is back to zero. Meanwhile a
runaway loop in the Flutter app can make unlimited *successful* calls without ever
hitting the limiter — which, with billing on, silently eats the shopkeeper's credits.

**Level:** MEDIUM

**Fix:** Point the limiter at the Redis instance already in your compose file, and count
successful requests for the credit-consuming routes.

---

## M-2 — Email uniqueness check only looks at the first 50 users

**STATUS: FIXED** (migration `025`) — `listUsers()` is gone; it is now one indexed lookup on
`public.users.email`.

Fixing the query alone would not have worked. `public.users` was storing the **raw** email while
Supabase Auth stores the lowercased one, so `Owner@Test.com` and `owner@test.com` could both exist
and the new lookup would have missed the duplicate anyway. Writes are normalized (registration and
staff creation), migration 025 normalizes existing rows, and a `UNIQUE (lower(email))` index makes
case-variant duplicates impossible at the database level rather than by convention.

A backstop maps Supabase's own duplicate error to a clean 409, covering an auth user that exists
with no profile row — which the lookup cannot see. 12 tests.


**Where:** [supabase-auth.service.ts:213-225](node-backend/services/auth-service/src/services/supabase-auth.service.ts#L213-L225)

`ensureEmailIsAvailable()` calls `auth.admin.listUsers()` — which is paginated and
returns only the first page (50 by default) — then searches that array in memory.

**Scenario:** Fine at 10 shopkeepers. At 60 users, a new signup with an email that
already exists passes the check, and the failure surfaces later as a raw Supabase error
("Registration failed") that the shopkeeper cannot act on. It is also two full user-list
downloads per signup, so registration gets slower as you grow.

**Level:** MEDIUM (becomes HIGH the moment you pass ~50 users)

**Fix:** Look the email up directly (a query on `public.users.email`, or Supabase's
filtered admin lookup) instead of listing all users.

---

## M-3 — Error messages leak token internals to the client

**STATUS: FIXED** — every branch now returns a fixed, generic 401. The decoded claims (including the
user's UUID and the server clock) no longer go to the caller, and unknown failures no longer return
raw `err.message`.

Timing detail (`iat`/`exp`/`now`) is still logged **server-side**, because it is genuinely what you
need to debug clock skew between a shopkeeper's phone and the server — but `sub` was dropped from the
log too, since that line ends up in aggregated logs. 7 tests, including that no raw unix timestamp
survives into the response.


**Where:** [auth.middleware.ts:78-99](node-backend/packages/middleware/src/auth.middleware.ts#L78-L99)

On a token failure, the middleware decodes the token body and appends
`| token claims: iat=…, exp=…, sub=<user uuid>, now=…` to the message that is **returned
to the caller** and printed to logs.

**Scenario:** An attacker probing your API gets your server's clock, the token lifetime,
and a valid internal user UUID handed back in a 401 body — useful groundwork for the
header-spoofing attack in C-3. Your production logs also fill with user identifiers.

**Level:** MEDIUM

**Fix:** Keep the debug detail in the server log only; return a plain "Session expired,
please log in again" to the client.

---

## M-4 — Duplicate-sale protection is global instead of per shop

**STATUS: FIXED** (migration `026`) — the constraint is now `UNIQUE (shop_id, idempotency_key)`,
matching how the key is actually queried.

⚠ **The write-up's second suggestion was deliberately NOT followed.** It proposed replacing the
pre-SELECT with `ON CONFLICT`. That would introduce a stock bug: `pos_checkout_atomic` deducts stock
*before* inserting the order, so when two identical checkouts race, both deduct. Today the loser hits
the unique violation, **raises**, and its whole transaction — including its stock deduction — rolls
back. With `ON CONFLICT DO NOTHING` the loser would carry on and commit, keeping its deduction and
double-deducting inventory for one sale. The raise is load-bearing; the migration header explains
this so it is not "tidied up" later. 3 tests pin it.


**Where:** [schema-prepared.sql:3798](database/ci/schema-prepared.sql#L3798) (`orders_idempotency_key_key UNIQUE (idempotency_key)`), [018_atomic_pos_checkout.sql:84-94](node-backend/docs/db/supabase/migrations/018_atomic_pos_checkout.sql#L84-L94)

The unique constraint is on `idempotency_key` alone, not on `(shop_id, idempotency_key)`,
while the lookup inside the RPC filters by both. The RPC also does SELECT-then-INSERT,
which is not atomic against two simultaneous identical requests.

**Scenario:** Once C-5 is fixed and the app starts sending keys, two shops can generate
the same key (or a client can reuse one). Shop B's completely unrelated sale is rejected
by a unique-violation that maps to a generic 500 — "something went wrong" on a sale that
was perfectly valid. Also, two rapid double-taps in the same millisecond can still slip
past the SELECT.

**Level:** MEDIUM

**Fix:** Replace the constraint with `UNIQUE (shop_id, idempotency_key)` and rely on
`ON CONFLICT` inside the RPC instead of the pre-SELECT.

---

## M-5 — Credits are charged after the response, and the charge can silently vanish

**STATUS: FIXED** — billing now charges **before** the handler runs and refunds anything not
delivered.

The ledger insert, the balance trigger and the `>= 0` CHECK were always atomic — that part was never
the bug. The bug was **ordering**: the charge ran on `res.on('finish')`, after the response had gone
out, so a charge that failed the CHECK meant the shop had already received the work for free with
only a console line to show for it. Charging first also closes the race where several parallel
requests each passed an independent pre-check.

Refunded outcomes: any error status, `202` (queued — the work has not happened yet), and a
`duplicate: true` replay (one sale, retried — charging twice is exactly what a shopkeeper notices).
A failed refund is logged as an error naming the shop and amount, because it leaves them overcharged
and needs a human. 13 tests.


**Where:** [creditDeduction.middleware.ts:53-71](node-backend/services/core-service/src/middlewares/creditDeduction.middleware.ts#L53-L71), [016_billing_membership_credits.sql:25-30](node-backend/docs/db/supabase/migrations/016_billing_membership_credits.sql#L25-L30)

The ledger insert happens on `res.on('finish')`, fire-and-forget; a failure is only
`console.error`'d. The pre-check and the deduction are separate, so parallel requests can
both pass a check they should not. The table also has a `credits_balance >= 0` CHECK, so
a deduction that would go negative fails the insert — and is then just logged.

**Scenario (against you):** A shop with 10 credits fires 5 parallel report requests
(75 credits each). All 5 pass the pre-check, all 5 run, and the ledger writes fail on the
non-negative constraint. The shop got hundreds of credits of expensive compute for free
and you have no record of it. **Scenario (against the shopkeeper):** a `202` queued
checkout or an idempotent duplicate replay returns `2xx`, so it is billed as a fresh
sale — the shopkeeper is charged twice for one transaction and the Usage tab does not
explain why.

**Level:** MEDIUM

**Fix:** Do the check-and-deduct in one database function (or reserve first, refund on
failure), skip billing for `202` and `duplicate: true` responses, and alert on ledger
write failures instead of only logging them.

---

## M-6 — Everything sleeps, so the first sale of the day is the slowest

**STATUS: FIXED** — four parts:
1. `GET /health` on all three services, mounted before **both** the rate limiter and the gateway
   signature guard, so an uptime probe needs no token and does not eat a shopkeeper's request budget.
2. `min_machines_running = 1` on the gateway — the first sale of the day no longer wakes a chain of
   three services inside the app's timeout.
3. Fly `[checks]` on all three, so Fly knows whether the app is *serving*, not merely booted.
4. A fire-and-forget warm-up ping when the app opens, so the cold-start cost lands on the splash
   screen instead of the first real request.

Verified with a real HTTP test that boots core-service and confirms `/health` answers 200 without the
gateway secret **while business routes still return 401** — i.e. M-6 did not weaken C-3.


**Where:** [gateway fly.toml](node-backend/gateway/api-gateway/fly.toml), [core-service fly.toml](node-backend/services/core-service/fly.toml), [auth-service fly.toml](node-backend/services/auth-service/fly.toml) — all `min_machines_running = 0`, 256 MB, single region `sin`; [backend_api_service.dart:55](flutter-frontend/lib/services/backend/backend_api_service.dart#L55) 15s timeout. No service defines a `/health` route.

Three services must all wake up in a chain (gateway → core → Supabase) inside the app's
15-second budget, on 256 MB shared-CPU machines, from Singapore to Pakistan.

**Scenario:** 9 a.m., first customer. The shopkeeper logs in; nothing happens for
twenty seconds and then "network error". He force-closes the app and tries twice more
before it works. If it happens on a checkout instead of a login, it becomes C-5 (double
sale). Since no service exposes `/health`, you also cannot see whether a machine is
actually ready, and you have no warm-up ping.

**Level:** MEDIUM

**Fix:** For the beta, set `min_machines_running = 1` on the gateway and core-service,
raise the client timeout for writes, add a `/health` route to each service, and consider
a warm-up call when the app opens.

---

## M-7 — Production CORS trusts every Firebase-hosted website in the world

**STATUS: FIXED** — the `*.web.app` / `*.firebaseapp.com` wildcard is deleted. Production accepts
only the origins in `ALLOWED_ORIGINS`.

Your real origins were already listed in the root `.env.example`, so nothing legitimate loses access
— but the gateway's own `.env.example` had only localhost, which would have broken the deployed web
app once the wildcard went. Both templates now carry the production origins with a note that there is
no fallback rule any more. A blocked origin logs a line naming `ALLOWED_ORIGINS`, so a genuine
missing entry is one look rather than an unexplained browser CORS failure. 16 tests, including the
phishing-clone case (`dukaandar-login.web.app` is refused).


**Where:** [corsOptions.ts:8-9](node-backend/packages/middleware/src/corsOptions.ts#L8-L9), [corsOptions.ts:55-58](node-backend/packages/middleware/src/corsOptions.ts#L55-L58)

In production, any origin matching `https://<anything>.web.app` or
`.firebaseapp.com` is allowed, with `credentials: true`.

**Scenario:** Anyone can spin up a free Firebase site in two minutes and have a page that
talks to your API from a shopkeeper's browser. It is not an instant account takeover
(your auth is a Bearer token, not a cookie), but it removes the browser's protection
entirely and makes a convincing phishing page — a copy of your login screen on
`dukaandar-login.web.app` that posts straight to your real API — trivial to build.

**Level:** MEDIUM

**Fix:** List your actual production origin(s) in `ALLOWED_ORIGINS` and delete the
wildcard Firebase rule.

---

## M-8 — Deleting an account leaves the shop's data behind

**STATUS: FIXED** (migration `022`) — deletion now genuinely cascades, and there is an export first.

⚠ **This one caught a bug I had introduced.** When I restored the critical fixes onto this branch I
brought `supabase-auth.service.ts` — which already called `fn_delete_owner_account` /
`fn_delete_staff_account` — but deliberately left migration 022 behind. Account deletion would have
failed at runtime with "function does not exist". Migration 022 is now included; I verified it covers
**all 23** tables carrying a `shop_id` FK before bringing it.

Added alongside: `GET /api/v1/shop/export` (admin-only, row-capped so a big shop cannot OOM a 256 MB
machine, reports what it truncated rather than returning a partial file that looks complete), and a
**typed confirmation** — the owner must type DELETE. That matters more now than before: deletion used
to remove only the auth user, so a mis-tap was survivable. It now takes the shop, every staff login
and every order with it. 5 tests.


**Where:** [auth.controller.ts:137-145](node-backend/services/auth-service/src/controllers/auth.controller.ts#L137-L145), [supabase-auth.service.ts:461-464](node-backend/services/auth-service/src/services/supabase-auth.service.ts#L461-L464)

`DELETE /api/v1/auth/account` deletes the Supabase auth user and nothing else. The
`shop`, `users`, `orders`, `products` and khata rows all stay. There is no confirmation
step and no data export.

**Scenario:** A beta shopkeeper taps "Delete account" to try it out. His login is gone
instantly and irreversibly — with no export of his month of sales — while his shop's
data lingers in your database owned by nobody, still counted in your reporting. He phones
you to get his data back and you have no supported way to give it to him.

**Level:** MEDIUM

**Fix:** Require typed confirmation, offer an export first, and make deletion a
soft-delete plus a documented cleanup, so a mis-tap is recoverable during the beta.

---

## M-9 — No offline mode at all

**STATUS: NOT FIXED — deliberately, and I recommend keeping it that way for the beta.**

This is the one MEDIUM I did not attempt. It is a **feature**, not a fix: a local queue, sync and
conflict handling, plus UI for pending/failed sales — and none of it can be verified without real
devices on real flaky connections, which is exactly where it would fail. Shipping a half-working
offline mode is worse than none, because a shopkeeper would trust it.

The write-up itself scoped it out, and the groundwork is now in place: C-5 gives every sale a stable
idempotency key, which is precisely what makes offline replay safe when you do build it.

**Tell the 10 shopkeepers up front that the app needs internet.** Expect this in their feedback — it
is the most common reason a POS trial gets abandoned in markets with patchy connectivity.


**Where:** [backend_api_service.dart](flutter-frontend/lib/services/backend/backend_api_service.dart) — every repository call goes straight to the network; nothing queues locally.

**Scenario:** The shop's internet drops for ten minutes — normal in most Pakistani
markets — and the POS is completely unusable. The shopkeeper writes sales on paper and
either never enters them or enters them wrong later. This is the single most common
reason a shopkeeper abandons a POS app during a trial, so expect it in your beta
feedback.

**Level:** MEDIUM (for beta expectations; would be CRITICAL for wide launch)

**Fix:** Out of scope to build before this beta — but say it explicitly to the 10
shopkeepers up front, and start with a local queue for `pos/checkout` (you already need
the idempotency key from C-5, which is exactly what makes offline replay safe).

---

## M-10 — Nobody is watching, and nothing is backed up on purpose

**STATUS: PARTIALLY FIXED — the code half is done; the rest needs accounts and an hour of your time.**

*Done in code:* `/health` on all three services (see M-6) and Fly `[checks]` so a machine that boots
but does not serve is visible. Plus `node-backend/docs/operations-runbook.md`, which is the practical
half of this issue.

*Still yours, and genuinely cannot be code:*
- **Point an uptime monitor at `/health`** — alert to WhatsApp/SMS, not email you will not read at 9am.
- **Make logs durable.** Errors currently go to `fly logs`, which is ephemeral — restart a machine and
  Tuesday's evidence is gone. Either forward Fly logs somewhere, or wire an error tracker;
  `errorHandler.middleware.ts` is the single place every unhandled error already passes through with a
  `requestId`. Deliberately not pre-wired, because a Sentry SDK with no DSN is worse than none.
- **Confirm Supabase PITR is enabled** — it is not on the free tier. For a beta holding real
  shopkeepers' money this is the line item worth paying for.
- **Do one restore drill before launch** and write down how long it took. That number is your real
  recovery time and the answer to "how long until my data is back". The runbook has the steps.


**Where:** no health endpoints, no error tracking and no alerting anywhere in the repo; [database/scripts/](database/scripts/) has dump/import helpers for CI but there is no documented production backup/restore; every service runs in one region (`sin`) with `auto_destroy_machines = true`.

**Scenario:** A bug corrupts a shop's stock numbers on a Tuesday. You find out on
Thursday from an angry phone call, with no error log to look at, no idea which release
caused it, and no verified point-in-time restore you have actually practised. With real
shopkeepers' money in the system, that is the difference between a bad day and losing
the beta.

**Level:** MEDIUM

**Fix:** Add health endpoints and an uptime check, wire up error tracking (Sentry or
equivalent) in the gateway and core-service, confirm Supabase point-in-time recovery is
enabled on your plan, and do one real restore drill before launch.

---

## M-11 — The web dashboard keeps the long-lived refresh token in `localStorage`

**STATUS: PARTIALLY FIXED — recovery added; the httpOnly cookie move is a real project.**

*Not done, with reason:* moving the refresh token to an `httpOnly` cookie needs a server to set that
cookie. The dashboard is a pure client-side Next.js app with **no API routes**, so this means adding
an auth layer that does not exist — a deliberate project, not a passing tweak, and not something to
change blind in an app I cannot run.

*Done:* the escape hatch the write-up called the minimum. `POST /api/v1/auth/logout-all` ends every
session on every device, wired into the dashboard as `signOutAllDevices()`. Without it a leaked
refresh token mints access tokens forever and the shopkeeper can do nothing; with it a suspected leak
is recoverable in one action.

⚠ **This uncovered a real bug in the earlier H-8 fix — see H-8 below.**


**Where:** [dashboard/lib/api.ts:12-40](dashboard/lib/api.ts#L12-L40)

Both the access token and the **refresh** token are stored in `localStorage`, which is
readable by any JavaScript running on the page. A refresh token is the long-lived
credential — whoever holds it can mint fresh access tokens indefinitely, and logging out
in one browser doesn't invalidate a copy someone already took.

**Scenario:** The dashboard pulls in a large client-side dependency tree (`three`,
`@react-three/*`, `gsap`, `lenis`, `framer-motion`). One compromised release of any of
them — or one XSS hole in a page that renders shop-supplied text — runs
`localStorage.getItem('dukaandar_refresh_token')` and quietly ships it out. The attacker
then has ongoing access to that shopkeeper's account with no password, and you have no
way to notice or revoke it short of forcing a global sign-out.

**Level:** MEDIUM

**Fix:** Keep the refresh token in an `httpOnly`, `Secure`, `SameSite=Strict` cookie set
by the server so page scripts cannot read it, and keep only the short-lived access token
in memory (not `localStorage`). At minimum, add a "sign out of all devices" action backed
by `auth.admin.signOut` so a suspected leak is recoverable.

---

## M-12 — No audit trail of who changed what

**STATUS: FIXED** (migration `027`) — every mutating request is recorded: who, which shop, what
entity, and the outcome.

Implemented as middleware rather than by instrumenting twenty services. That is a deliberate
trade-off: it captures the request rather than a full before/after diff, but it answers the question
actually asked in a support call — "who changed the price of rice", "who deleted that order" — and it
does so without touching the business logic, which is where the risk of breaking a working system
lives.

Credential-shaped fields are stripped at any nesting depth, so the audit table cannot become the thing
that leaks what C-1 removed. Reads are not logged. Writes are fire-and-forget **and try/caught** — a
test initially proved a synchronous failure would escape the `finish` listener as an uncaught
exception and could take the process down; auditing must never be able to kill a sale. 18 tests.
Query examples are in the operations runbook.


**Where:** no history table in the migrations; [product.service.ts](node-backend/services/core-service/src/services/product.service.ts), [order.routes.ts](node-backend/services/core-service/src/routes/order.routes.ts) — updates and deletes overwrite in place.

**Scenario:** A shopkeeper says "Rs. 8,000 of stock is missing and someone changed the
price of rice." You have no record of which staff account edited that product, or who
deleted that order, or when. You cannot answer him, and you cannot tell a real bug from
staff theft — during exactly the period when you need clean feedback about your own code.

**Level:** MEDIUM

**Fix:** Add a lightweight `audit_log` (user, shop, action, entity, before/after,
timestamp) written on product, price, order, stock and staff changes.

---

# LOW

## L-1 — Two API routes point at services that don't exist

**Where:** [serviceUrls.ts:49-50](node-backend/gateway/api-gateway/src/proxy/serviceUrls.ts#L49-L50), [docker-compose.yml](node-backend/docker-compose.yml) — `ai-service` and `forecasting-service` are `sleep infinity` placeholders.

`/api/v1/ai/*` and `/api/v1/forecasting/*` are routed to services that only sleep.
Nothing in the Flutter app calls them today, so the impact is limited to a confusing
`503 SERVICE_UNAVAILABLE` if anyone ever does.

**Level:** LOW — **Fix:** remove the routes until the services exist.

---

## L-2 — The committed frontend config points at localhost

**Where:** [flutter-frontend/.env](flutter-frontend/.env) — `BACKEND_URL=http://localhost:3000`, `USE_BACKEND=true`.

**Scenario:** Someone builds the beta APK from a clean checkout without swapping the
`.env`, and the app cannot reach anything — every screen shows a network error, and it
looks like the backend is down. A ten-minute panic for a one-line cause.

**Level:** LOW — **Fix:** build-time `--dart-define` for the production URL, and remove
the tracked `.env` (see H-2).

---

## L-3 — A stale token can be handed out as if it were valid

**Where:** [backend_token_service.dart:24-44](flutter-frontend/lib/services/backend/backend_token_service.dart#L24-L44)

If the stored `expiresAt` is missing or unparseable it is treated as `0`, and the code
then returns the stored token as valid. (The `Math` helper class at the bottom of the
file is also dead code.)

**Scenario:** After a partial write to secure storage, the app keeps sending an expired
token, gets a 401, and depends on the refresh path — which has the logout bug in H-5.
The shopkeeper sees an unexplained logout.

**Level:** LOW — **Fix:** treat a missing expiry as "expired" and refresh.

---

## L-4 — Registration tells strangers which emails are registered

**Where:** [supabase-auth.service.ts:221-224](node-backend/services/auth-service/src/services/supabase-auth.service.ts#L221-L224) — returns "An account with this email already exists."

**Scenario:** Someone can check whether a given shopkeeper is your customer, one email
at a time, which is useful for targeted phishing (combined with M-7). Minor for a 10-user
beta, worth closing before public launch.

**Level:** LOW — **Fix:** return the same neutral "check your email" response either way.

---

## L-5 — Large request bodies accepted with no image size checks

**Where:** [core-service/src/app.ts:54](node-backend/services/core-service/src/app.ts#L54) — `express.json({ limit: '5mb' })` on 256 MB machines.

**Scenario:** A few shopkeepers uploading big product photos at once can push a 256 MB
machine into out-of-memory restarts, taking down every shop's POS for a minute.

**Level:** LOW — **Fix:** validate/resize images client-side and lower the JSON limit for
non-upload routes.

---

# Launch checklist — the short version

**Must fix before you hand the app to 10 shopkeepers:**

| # | Issue | Status |
|---|---|---|
| 1 | **C-4** — starting credits + credit-grant endpoint | ✅ fixed (needs migration 020 + env) |
| 2 | **C-1 + C-2** — plain-text passwords, `/users` scoping | ✅ fixed (needs migration 019) |
| 3 | **C-3** — private services + gateway shared secret | ✅ fixed (needs env + release public IPs) |
| 4 | **C-5** — idempotency key + longer checkout timeout | ✅ fixed (ship app and backend together) |
| 5 | **C-6** — close public registration | ⏸ reverted by design — app is open to all emails |
| 6 | **H-1** — outstanding-amount calculation | ✅ fixed (needs migration 023) |
| 7 | **H-2** — untrack `.env`, rotate leaked keys | ✅ code fixed — ⚠ **you must still rotate the keys** |
| 8 | **H-4 + H-5** — real errors, stop random logouts | ✅ fixed |

**Every HIGH item is now closed:** H-1 and H-6 (migration 023), H-2 (code — rotation still yours),
H-3 and H-8 (fixed alongside the critical work), H-4 and H-5 (client), H-7 (migration 024).

**Then, in the first week:** M-6 (keep one machine warm) and M-10 (monitoring + a practised
restore) are the two that would most change how a bad day goes.

**Tell the shopkeepers up front:** the app needs internet to work (M-9).

---

## What was checked and looked fine

So you know where *not* to spend time:

- **Tenant scoping in the business services** — products, variants, customers, vendors,
  salesmen, orders, purchases, expenses, guarantors, installments, account-book,
  notifications and reports all correctly take `shop_id` from the gateway header and
  filter on it. The `/users` routes (C-2) are the only exception found.
- **POS stock race** — `pos_checkout_atomic` uses compare-and-swap
  (`UPDATE … WHERE stock >= qty`) inside one transaction, with retry and an async
  fallback queue. Concurrent cashiers cannot oversell.
- **Worker job claiming** — `claim_next_checkout_job` uses `FOR UPDATE SKIP LOCKED`, so
  multiple machines won't double-process a queued sale.
- **JWT verification** — proper signature checking with `jose` (HS256 secret and ES256
  via JWKS); no `alg: none` or unverified-decode path at the gateway.
- **Mass-assignment protection** — `shop.update` and `users.update` both run bodies
  through `pickFields` whitelists, so a client cannot set `credits_balance`,
  `membership_plan` or `role` through them.
- **OTP handling** — 6-digit code from `crypto.randomInt`, stored only as a salted
  SHA-256 hash, compared with `timingSafeEqual`, with expiry, a 5-attempt cap and a
  resend cooldown.
- **Secret handling on the server** — the Supabase service-role key stays server-side in
  all three backend services; no `.env` from `node-backend` is committed.
- **Error handling** — a global error handler maps `AppError`s to clean codes and returns
  a generic message for unexpected errors instead of leaking stack traces (M-3 is the
  one exception).


---

# Deploying these fixes

Nothing here works until the migrations and environment variables are applied. In order:

### 1. Migrations — run these in Supabase (you run them, not me)

| File | What it does | Risk |
|---|---|---|
| [019_drop_plain_password.sql](node-backend/docs/db/supabase/migrations/019_drop_plain_password.sql) | Drops `users.plain_password` | Destructive **on purpose**. The values must not exist. Passwords cannot be migrated — a shopkeeper who needs a staff password sets a new one from the staff screen. |
| [020_signup_credit_grant.sql](node-backend/docs/db/supabase/migrations/020_signup_credit_grant.sql) | Sets the `credits_balance` default to 500 and backfills shops sitting at zero | ⚠ **Read before running.** The backfill grants 500 credits to every currently-empty shop. Delete that statement if you would rather top shops up individually. |

| [023_checkout_payable_total_and_ownership.sql](node-backend/docs/db/supabase/migrations/023_checkout_payable_total_and_ownership.sql) | H-1 + H-6: records the customer's outstanding against the true payable total, stores the real salesman commission, and rejects cross-shop customer/salesman/user references | Redefines `pos_checkout_atomic`. Safe to re-run. **Does not touch existing rows** — khata entries already written with the old, too-small amount stay as they are; see the note below. |
| [024_login_attempt_lockout.sql](node-backend/docs/db/supabase/migrations/024_login_attempt_lockout.sql) | H-7: `login_attempts` table + atomic failure counter, for per-account lockout | New table and two functions only. No existing data touched. |

Run 019 **after** deploying the new backend (the old build still writes that column).
Run 023 **together with** the app update — the client now sends `salesmanComission`, which the new
function needs to compute the commission (an older client just yields a commission of 0).

ℹ️ **No khata reconciliation needed.** Migration 023 does not retro-correct rows already written
with the old, too-small outstanding amount — but the app has not reached testers yet, so there are
no real sales to correct. Running 023 before launch means every khata entry is right from the first
sale. (If this were run after testers had been selling on credit, those earlier balances would need
a one-off manual reconciliation.)

### 2. Environment variables

New and **required** — the services now fail to start without them, deliberately, so a missing
secret cannot silently mean "no protection":

| Variable | Where | Notes |
|---|---|---|
| `GATEWAY_SHARED_SECRET` | gateway, auth-service, core-service | Must be **identical** in all three. Min 32 chars. Generate: `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"` |
| `SIGNUP_CREDIT_GRANT` | auth-service | Defaults to 500. Keep in step with migration 020. |
| `INTERNAL_ADMIN_KEY` | core-service | Enables `POST /api/v1/billing/grant`. Min 32 chars. Unset = endpoint refuses everything. |
| `OPENAI_API_KEY` | core-service | **New (H-2).** AI product descriptions, moved out of the Flutter app where the old key shipped inside every APK. Unset = the AI button returns a clean 503 instead of breaking. |
| `OPENAI_MODEL` | core-service | Optional, defaults to `gpt-4o-mini`. |

All are documented in the updated `.env.example` files.

### 3. Fly.io — release the public IPs

The `[[services]]` blocks are gone from both service configs, but an app that was already
deployed keeps any IP it was given:

```
fly ips list -a dukaandar-core-service
fly ips release <ip> -a dukaandar-core-service
fly ips list -a dukaandar-auth-service
fly ips release <ip> -a dukaandar-auth-service
```

Confirm `CORE_SERVICE_URL` / `AUTH_SERVICE_URL` on the gateway point at `*.internal` addresses.

### 4. Deploy order

Backend and Flutter app **together**. The checkout endpoint now requires an idempotency key, so
an old client build cannot complete a sale against the new backend.

### 5. Topping up a shop

```
curl -X POST https://<gateway>/api/v1/billing/grant   -H "Content-Type: application/json"   -H "X-Internal-Admin-Key: $INTERNAL_ADMIN_KEY"   -d '{"shopId": 4, "credits": 1000, "reason": "jazzcash 500rs"}'
```

Recorded in `shop_credit_ledger`, so the shopkeeper sees it in their usage history.
