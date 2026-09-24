from datetime import date, datetime

from fastapi.testclient import TestClient
from zett_agent import ModelUsageActivityRecord

from zett._compat import UTC
from zett.infra.persistence.dao import model_usage_activity_storage
from zett.main import app


def usage(
    occurred_at: datetime,
    *,
    input_tokens: int,
    output_tokens: int,
    provider: str | None = "deepseek",
    model: str | None = "deepseek-chat",
) -> ModelUsageActivityRecord:
    return ModelUsageActivityRecord(
        session_id="session",
        request_id="request",
        provider=provider,
        model=model,
        occurred_at=occurred_at,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
    )


async def test_usage_activity_storage_aggregates_requests_by_utc_day():
    await model_usage_activity_storage.record(
        usage(datetime(2026, 9, 18, 23, 59, tzinfo=UTC), input_tokens=100, output_tokens=20)
    )
    await model_usage_activity_storage.record(
        usage(datetime(2026, 9, 19, 0, 1, tzinfo=UTC), input_tokens=200, output_tokens=40)
    )
    await model_usage_activity_storage.record(
        usage(datetime(2026, 9, 19, 12, 0, tzinfo=UTC), input_tokens=300, output_tokens=60)
    )

    rows = await model_usage_activity_storage.activity(
        start=date(2026, 9, 18),
        end=date(2026, 9, 19),
    )

    assert [(row.date, row.requests, row.total_tokens) for row in rows] == [
        (date(2026, 9, 18), 1, 120),
        (date(2026, 9, 19), 2, 600),
    ]


def test_settings_usage_activity_returns_zero_filled_days():
    with TestClient(app) as client:
        response = client.get("/api/settings/usage-activity?days=3")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    assert all(row["requests"] == 0 for row in rows)
    assert [date.fromisoformat(row["date"]) for row in rows] == sorted(date.fromisoformat(row["date"]) for row in rows)


async def test_model_usage_activity_groups_by_provider_and_model():
    await model_usage_activity_storage.record(
        usage(
            datetime(2026, 9, 19, 1, 0, tzinfo=UTC),
            input_tokens=100,
            output_tokens=20,
            provider="deepseek",
            model="deepseek-flash",
        )
    )
    await model_usage_activity_storage.record(
        usage(
            datetime(2026, 9, 19, 2, 0, tzinfo=UTC),
            input_tokens=200,
            output_tokens=40,
            provider="openai",
            model="gpt-test",
        )
    )

    rows = await model_usage_activity_storage.model_activity(
        start=date(2026, 9, 19),
        end=date(2026, 9, 19),
    )

    assert [(row.provider, row.model, row.days[0].requests, row.days[0].total_tokens) for row in rows] == [
        ("deepseek", "deepseek-flash", 1, 120),
        ("openai", "gpt-test", 1, 240),
    ]


async def test_settings_model_usage_activity_is_zero_filled_and_sorted():
    await model_usage_activity_storage.record(
        usage(
            datetime.now(UTC),
            input_tokens=100,
            output_tokens=20,
            provider="deepseek",
            model="deepseek-flash",
        )
    )
    with TestClient(app) as client:
        response = client.get("/api/settings/model-usage-activity?days=3")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["provider"] == "deepseek"
    assert rows[0]["model"] == "deepseek-flash"
    assert len(rows[0]["days"]) == 3
    assert sum(day["requests"] for day in rows[0]["days"]) == 1
    assert sum(day["total_tokens"] for day in rows[0]["days"]) == 120
