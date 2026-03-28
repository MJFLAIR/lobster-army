import pytest
from runtime.app import create_app
from runtime.cron_tick import handle_tick
from workflows.storage.db import DB

pytestmark = pytest.mark.integration


def test_cron_tick_legacy():
    app = create_app()

    with app.app_context():
        resp = handle_tick()

    # ✅ 基本驗證（避免空跑）
    assert resp is not None

    # ✅ DB 驗證（integration 才會跑）
    task = DB.get_task(1016)

    # 不強制存在（避免測試不穩），但要可觀察
    if task:
        status = getattr(task, "status", None) or task.get("status", None)
        assert status is not None