from datetime import datetime, timezone

import pytest

from src.pipeline.cleanup import delete_expired_items


class FakeDeleteResult:
    rowcount = 3


class FakeSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeDeleteResult()


@pytest.mark.asyncio
async def test_delete_expired_items_uses_expires_at_cutoff():
    session = FakeSession()
    now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)

    count = await delete_expired_items(session, now)

    assert count == 3
    assert len(session.statements) == 1
    statement = session.statements[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "DELETE FROM items" in compiled
    assert "items.expires_at IS NOT NULL" in compiled
    assert "items.expires_at < '2026-05-26 08:00:00+00:00'" in compiled
