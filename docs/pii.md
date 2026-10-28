# PII and hardening

## What is stored and where

| Data | Where it lives | Reaches the warehouse? | Treatment |
|---|---|---|---|
| IP address | never stored raw | No | Truncated (/24 for IPv4, /48 for IPv6), then HMAC-SHA256 with `IP_SALT`. Used only for rate limiting. |
| Raw user agent | `app.request_metadata.user_agent_raw` | No | Only the parsed browser and OS families flow downstream. |
| Accept-Language | `app.request_metadata.accept_language` | No | Kept for debugging only. |
| Message | `app.submissions.message` | Yes, into Snowflake | Needed for the word frequencies. The page shows a "no personal data" notice. Never logged. Max 280 characters. Readers can see it in `MARTS.FCT_SUBMISSIONS`, which is accepted. |
| Password | never stored | No | Only the outcome is recorded in `auth_attempts`. |

## How the database enforces it

- Only `app.submissions` is extracted. `el_reader` has SELECT on that table
  and nothing else, so the auxiliary tables cannot be read by the EL job even
  by mistake.
- `web_writer` can insert into all three tables but cannot read the message
  or `request_metadata`. It reads `auth_attempts` for the rate limit.
- Snowflake readers see `MARTS` only (see `grants-matrix.md`). They cannot
  read `RAW` or `STAGING`, cannot read account usage views, and cannot raise
  their 30 s statement timeout.
- The Semantic Layer queries with its own read-only credential, so metric
  queries see the same `MARTS` and nothing more.

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

- Hard deletes in Postgres are not propagated to Snowflake. Soft deletes
  (`deleted_at`) are. A soft-deleted message stays in `RAW.SUBMISSIONS`.
- Messages are free text. A user could type personal data despite the notice.
- The warehouse is a third-party cloud service, and the dbt platform sees
  metadata and metric results. Messages reach Snowflake, and metric queries return
  aggregates only. Do not put real personal data in this demo.
