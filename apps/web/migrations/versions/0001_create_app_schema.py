"""Create the app schema objects and least-privilege grants.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE_SQL = [
    """
    CREATE TABLE app.submissions (
      id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      message        varchar(280) NOT NULL
                     CHECK (char_length(btrim(message)) BETWEEN 1 AND 280),
      browser_family text NOT NULL,
      os_family      text NOT NULL,
      created_at     timestamptz NOT NULL DEFAULT now(),
      updated_at     timestamptz NOT NULL DEFAULT now(),
      deleted_at     timestamptz NULL
    )
    """,
    """
    CREATE INDEX submissions_updated_at_idx
      ON app.submissions (updated_at, id)
    """,
    """
    CREATE TABLE app.request_metadata (
      submission_id   bigint PRIMARY KEY
                      REFERENCES app.submissions(id) ON DELETE CASCADE,
      user_agent_raw  text NOT NULL CHECK (char_length(user_agent_raw) <= 1024),
      ip_hash         char(64) NOT NULL,
      accept_language varchar(128),
      created_at      timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE app.auth_attempts (
      id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      attempted_at  timestamptz NOT NULL DEFAULT now(),
      ip_hash       char(64) NOT NULL,
      success       boolean NOT NULL,
      reason        text NOT NULL CHECK (reason IN
                    ('ok','bad_password','rate_limited','csrf','invalid_input')),
      submission_id bigint NULL REFERENCES app.submissions(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE INDEX auth_attempts_ip_time_idx
      ON app.auth_attempts (ip_hash, attempted_at DESC)
    """,
    """
    CREATE FUNCTION app.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      NEW.updated_at = now();
      RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER submissions_set_updated_at
      BEFORE UPDATE ON app.submissions
      FOR EACH ROW EXECUTE FUNCTION app.set_updated_at()
    """,
    # web_writer: insert-only. SELECT (id) on submissions is what
    # `INSERT ... RETURNING id` needs; the message stays unreadable.
    "GRANT USAGE ON SCHEMA app TO web_writer, el_reader",
    "GRANT INSERT ON app.submissions, app.request_metadata, app.auth_attempts"
    " TO web_writer",
    "GRANT SELECT (id) ON app.submissions TO web_writer",
    "GRANT SELECT ON app.auth_attempts TO web_writer",
    "GRANT USAGE ON SEQUENCE app.submissions_id_seq, app.auth_attempts_id_seq"
    " TO web_writer",
    # el_reader: the only table that may leave Postgres.
    "GRANT SELECT ON app.submissions TO el_reader",
]

DOWNGRADE_SQL = [
    "REVOKE USAGE ON SCHEMA app FROM web_writer, el_reader",
    "DROP TABLE app.auth_attempts",
    "DROP TABLE app.request_metadata",
    "DROP TABLE app.submissions",
    "DROP FUNCTION app.set_updated_at()",
]


def upgrade() -> None:
    """Create tables, indexes, trigger and grants."""
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    """Drop everything this revision created (the schema itself is init's)."""
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
