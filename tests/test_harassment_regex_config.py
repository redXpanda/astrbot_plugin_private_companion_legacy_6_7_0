from __future__ import annotations

import json
from pathlib import Path

import pytest

from .test_boundary_feedback_integration import _BoundaryHarness


@pytest.mark.parametrize("text", ["吃完就上床吧 该休息啦", "开房"])
def test_keyword_detection_is_disabled_by_default(text):
    host = _BoundaryHarness()
    host.relationship_harassment_regex = r"上床|开房"

    assert host._classify_local_boundary_feedback_signal(text)["type"] == "normal"


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        (r"开房", "开房", "action"),
        (r"开房", "吃完就上床吧 该休息啦", "normal"),
        (r"上床(?!休息)", "上床休息", "normal"),
        (r"上床(?!休息)", "上床", "action"),
        ("", "开房", "normal"),
        ("[", "开房", "normal"),
    ],
)
def test_enabled_detection_uses_configured_regex(pattern, text, expected):
    host = _BoundaryHarness()
    host.enable_relationship_harassment_regex = True
    host.relationship_harassment_regex = pattern

    signal = host._classify_local_boundary_feedback_signal(text)

    assert signal["type"] == expected
    if expected == "action":
        assert signal["suitable_tier"] == "beyond"


def test_disabling_keywords_preserves_coercion_detection():
    host = _BoundaryHarness()

    signal = host._classify_local_boundary_feedback_signal("不许拒绝")

    assert signal["type"] == "action"
    assert signal["suitable_tier"] == "beyond"


def test_schema_exposes_default_off_switch_and_regex():
    schema = json.loads(
        (Path(__file__).parents[1] / "_conf_schema.json").read_text(encoding="utf-8")
    )["experimental_motivation_config"]["items"]

    assert schema["enable_relationship_harassment_regex"]["default"] is False
    assert schema["relationship_harassment_regex"]["type"] == "text"
    host = _BoundaryHarness()
    host.enable_relationship_harassment_regex = True
    host.relationship_harassment_regex = schema["relationship_harassment_regex"][
        "default"
    ]
    assert host._classify_local_boundary_feedback_signal("开房")["type"] == "action"
