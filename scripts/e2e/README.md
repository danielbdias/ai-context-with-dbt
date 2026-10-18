# End-to-end harness

A pytest suite run from the host against an isolated compose project
(`-p aictx-e2e`, fresh volumes, host ports 15432/18123/19000/...), so it can run
next to the dev stack.

## Run

```bash
task e2e                              # up, wait healthy, pytest, always down -v
E2E_KEEP=1 task e2e                   # leave the stack up to debug
task e2e E2E_PROFILES=core,app,el    # extra compose profiles (default core,app)
```

`e2e.env` holds test-only credentials and ports. It replaces `.env` for this
project. The suite is marked `e2e` and is excluded from `task test`.

## Add a stage

1. Add `scripts/e2e/tests/test_NN_<name>.py` (files run in name order).
2. Use the helpers in `scripts/e2e/helpers.py`:
   `pg_query`, `pg_query_as(user, password, sql)`, `migrate(rev, direction=)`,
   `ch_command` (DDL/INSERT), `ch_query(sql, user=, password=)` (raises on denied/constraint
   errors), `compose_run(service, ..., profiles=[...])` for one-shot services,
   `web_client()` for the web app.
3. Add the new profile(s) to `E2E_PROFILES` in `Taskfile.yml`, and any new
   variables to `e2e.env`.
