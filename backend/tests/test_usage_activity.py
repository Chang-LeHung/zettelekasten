from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from zett_agent import ModelUsageActivityRecord

from zett.infra.dao import model_usage_activity_storage
from zett.main import app


def usage(
    occurred_at: datetime,
    *,
    input_tokens: int,
    output_tokens: int,
) -> ModelUsageActivityRecord:
    return ModelUsageActivityRecord(
        session_id="session",
        request_id="request",
        provider="deepseek",
        model="deepseek-chat",
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
