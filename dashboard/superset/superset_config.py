"""Superset settings for the demo. Every secret comes from the environment.

The image loads this file from PYTHONPATH (/app/pythonpath). Metadata lives in
database `superset` of the shared Postgres, owned by `superset_meta`. Example
datasets are never loaded: init.sh imports only the committed word-cloud bundle.
"""

import os
from urllib.parse import quote_plus

# The image refuses to start with its default key.
SECRET_KEY: str = os.environ["SUPERSET_SECRET_KEY"]

_META_PASSWORD: str = quote_plus(os.environ["POSTGRES_SUPERSET_META_PASSWORD"])
SQLALCHEMY_DATABASE_URI: str = (
    f"postgresql+psycopg2://superset_meta:{_META_PASSWORD}"
    f"@{os.environ['POSTGRES_HOST']}:{os.environ['POSTGRES_PORT']}/superset"
)
