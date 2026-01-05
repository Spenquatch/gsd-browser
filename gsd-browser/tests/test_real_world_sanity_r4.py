from __future__ import annotations


def test_r4_default_scenarios_match_plan_ids() -> None:
    from gsd_browser.real_world_sanity import DEFAULT_SCENARIOS

    assert [scenario.id for scenario in DEFAULT_SCENARIOS] == [
        "wikipedia-openai-first-sentence",
        "hackernews-top-story",
        "github-cdp-heading",
        "huggingface-papers-botwall-probe",
    ]


def test_r4_default_scenarios_expected_values_are_valid() -> None:
    from gsd_browser.real_world_sanity import DEFAULT_SCENARIOS

    expected_values = {scenario.expected for scenario in DEFAULT_SCENARIOS}
    assert expected_values.issubset({"pass", "soft_fail"})
    assert "pass" in expected_values
    assert "soft_fail" in expected_values
