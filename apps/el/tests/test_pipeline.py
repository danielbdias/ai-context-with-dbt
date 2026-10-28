"""Pipeline wiring and retry logic: no network."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dlt.pipeline.exceptions import PipelineStepFailed
from el import pipeline
from el.settings import Settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("POSTGRES_EL_READER_PASSWORD", "pg")
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "org-acct")
    monkeypatch.setenv("SNOWFLAKE_EL_LOADER_PASSWORD", "sf")
    return Settings()  # type: ignore[call-arg]


def test_resource_selects_only_submissions_incrementally(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        pipeline, "sql_table", lambda *a, **kw: captured.update(kw, args=a)
    )
    pipeline.build_resource(settings)
    assert captured["table"] == "submissions"
    assert captured["schema"] == "app"
    assert captured["write_disposition"] == "merge"
    assert captured["primary_key"] == "id"
    cursor = captured["incremental"]
    assert cursor.cursor_path == "updated_at"
    assert cursor.lag == 5


def test_destination_is_snowflake_loading_into_raw(
    settings: Settings, tmp_path: Path
) -> None:
    destination = pipeline.build_destination(settings)
    assert destination.destination_name == "snowflake"
    built = pipeline.build_pipeline(settings, str(tmp_path))
    assert built.dataset_name == "raw"


def _failure() -> PipelineStepFailed:
    stub = SimpleNamespace(has_pending_data=False, pipeline_name="t")
    return PipelineStepFailed(stub, "load", None, RuntimeError("boom"))  # type: ignore[arg-type]


def test_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise _failure()
        return "ok"

    assert pipeline.with_retries(flaky, 3, 0) == "ok"
    assert len(calls) == 3


def test_retries_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    calls: list[int] = []

    def broken() -> None:
        calls.append(1)
        raise _failure()

    with pytest.raises(PipelineStepFailed):
        pipeline.with_retries(broken, 2, 0)
    assert len(calls) == 2


def test_main_returns_nonzero_when_the_load_fails(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EL_MAX_ATTEMPTS", "1")

    def unreachable(*_: object) -> None:
        raise _failure()

    monkeypatch.setattr(pipeline, "run_once", unreachable)
    assert pipeline.main() == 1
