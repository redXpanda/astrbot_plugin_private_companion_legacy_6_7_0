"""Regression coverage for agenda reads on the message-processing thread."""

from copy import deepcopy
from datetime import datetime
from unittest.mock import patch

import agenda_contracts
import agenda_runtime
import schedule_reconciler
from agenda_runtime import AgendaRuntimeMixin
from unified_agenda import build_unified_agenda

NOW = datetime.fromisoformat("2026-11-10T15:00:00+08:00")


class Host(AgendaRuntimeMixin):
    def __init__(self):
        self.data = {
            "daily_plan": {
                "date": "2026-11-10",
                "items": [{"activity": "study", "time": "14:30", "end": "16:00"}],
            }
        }

    def _agenda_now(self):
        return NOW


def test_repeated_agenda_reads_do_not_repeat_store_migration():
    host = Host()
    with patch.object(
        agenda_runtime, "migrate_store", wraps=agenda_runtime.migrate_store
    ) as migrate:
        first = host._agenda_build(now=NOW)
        first["plans"].clear()
        second = host._agenda_build(now=NOW)
        host._agenda_activities_store()
        assert second["plans"]
        assert migrate.call_count == 1

        host.data["daily_plan"]["items"][0]["activity"] = "writing"
        host.data["daily_plan"]["items"][0]["title"] = "writing"
        changed = host._agenda_build(now=NOW)
        assert changed["plans"][0]["title"] == "writing"
        assert migrate.call_count == 1

        host.data = {"daily_plan": {"date": "2026-11-10", "items": []}}
        assert host._agenda_build(now=NOW)["plans"] == []
        assert migrate.call_count == 2


def test_activity_capture_invalidates_agenda_without_migrating_again():
    host = Host()
    with patch.object(
        agenda_runtime, "migrate_store", wraps=agenda_runtime.migrate_store
    ) as migrate:
        first = host._agenda_build(now=NOW)
        host._agenda_capture_hard_fact(
            {
                "activity_id": "new-evidence",
                "title": "actual study",
                "start_at": "2026-11-10T14:30:00+08:00",
                "end_at": "2026-11-10T16:00:00+08:00",
                "evidence_kind": "tool_action",
                "subject_actor_id": "bot_self",
            }
        )
        second = host._agenda_build(now=NOW)
        assert not first["activities"]
        assert second["activities"][0]["activity_id"] == "new-evidence"
        assert migrate.call_count == 1


def test_reconciliation_parsing_and_plan_classification_scale_with_records():
    plans = [
        {
            "plan_id": f"plan-{index}",
            "title": "study",
            "start_at": "2026-11-10T14:30:00+08:00",
            "end_at": "2026-11-10T16:00:00+08:00",
            "subject_actor_id": "bot_self",
            "actor_type": "bot",
        }
        for index in range(12)
    ]
    activities = [
        {
            "activity_id": f"activity-{index}",
            "title": "study",
            "start_at": "2026-11-10T14:30:00+08:00",
            "end_at": "2026-11-10T15:30:00+08:00",
            "subject_actor_id": "bot_self",
            "actor_type": "bot",
            "evidence_kind": "interaction",
        }
        for index in range(100)
    ]
    before = deepcopy((plans, activities))
    with (
        patch.object(
            schedule_reconciler, "_interval", wraps=schedule_reconciler._interval
        ) as intervals,
        patch.object(
            schedule_reconciler,
            "_is_chat_plan",
            wraps=schedule_reconciler._is_chat_plan,
        ) as classify,
    ):
        result = build_unified_agenda(plans=plans, activities=activities, now=NOW)
        assert intervals.call_count < 10 * (len(plans) + len(activities))
        assert classify.call_count <= len(plans)
    assert (plans, activities) == before
    assert len(result["activities"]) == 100
    assert len(result["reconciliation_candidates"]) == 24
    assert all(
        len(item["activity_ids"]) == 3 for item in result["reconciliation_candidates"]
    )


def test_window_projection_reuses_intervals_and_keeps_midnight_semantics():
    activity = {
        "activity_id": "overnight",
        "title": "rest",
        "date": "2026-11-10",
        "time": "23:30",
        "end": "00:30",
        "start_at": "2026-11-10T23:30:00+08:00",
        "end_at": "2026-11-11T00:30:00+08:00",
        "subject_actor_id": "bot_self",
        "actor_type": "bot",
        "evidence_kind": "tool_action",
    }
    with patch.object(
        agenda_contracts, "_item_datetime", wraps=agenda_contracts._item_datetime
    ) as parse:
        agenda = build_unified_agenda(plans=[], activities=[activity], now=NOW)
        assert parse.call_count < 20
    assert [window["slug"] for window in agenda["windows"] if window["observed"]] == [
        "late_night"
    ]
    assert agenda["entries"]
    legacy = {
        key: value
        for key, value in activity.items()
        if key not in {"start_at", "end_at"}
    }
    start, end = agenda_contracts.item_interval(legacy)
    assert start.isoformat() == "2026-11-10T23:30:00+08:00"
    assert end.isoformat() == "2026-11-11T00:30:00+08:00"
