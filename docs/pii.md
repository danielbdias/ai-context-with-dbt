# PII and hardening

## What is stored and where

| Data | Where it lives | Reaches the warehouse? | Treatment |
|---|---|---|---|
| IP address | never stored raw | No | Truncated (/24 for IPv4, /48 for IPv6), then HMAC-SHA256 with `IP_SALT`. Used only for rate limiting. |
| Raw user agent | `app.request_metadata.user_agent_raw` | No | Only the parsed browser and OS families flow downstream. |
| Accept-Language | `app.request_metadata.accept_language` | No | Kept for debugging only. |
| Message | `app.submissions.message` | Yes | Needed for the word cloud. The page shows a "no personal data" notice. Never logged. Max 280 characters. Readers can see it in `marts.fct_submissions`, which is accepted. |
| Password | never stored | No | Only the outcome is recorded in `auth_attempts`. |

## How the database enforces it

- Only `app.submissions` is extracted. `el_reader` has SELECT on that table
  and nothing else, so the auxiliary tables cannot be read by the EL job even
  by mistake.
- `web_writer` can insert into all three tables but cannot read the message
  or `request_metadata`. It reads `auth_attempts` for the rate limit.
- ClickHouse readers see `marts` only (see `grants-matrix.md`). They cannot
  read `raw`, `staging` or `system.query_log`, and cannot lift the `reader`
  profile limits.

## App hardening

- `APP_PASSWORD` comes from the environment and is compared with
  `hmac.compare_digest`. The fixed value `dssbr` is intentionally insecure and
  for the local demo only.
- Rate limit: N failures per `ip_hash` per window (default 5 per 15 minutes).
  Under Docker Desktop NAT it is effectively global.
- CSRF uses a signed double-submit cookie with `SameSite=Strict`.
- Message length is checked in the HTML form, the server model and a database
  CHECK.
- CSP `default-src 'self'` and a "DEMO ONLY" banner.
- Message bodies are never logged.

## Known limits

- Hard deletes in Postgres are not propagated to ClickHouse. Soft deletes
  (`deleted_at`) are.
- Messages are free text. A user could type personal data despite the notice.
