"""Regression tests for the default automatic-compaction contract."""

from hermes_cli.config_defaults import DEFAULT_CONFIG


def test_default_compression_contract_is_enabled_and_conservative():
    compression = DEFAULT_CONFIG["compression"]

    assert compression["enabled"] is True
    assert compression["threshold"] == 0.80
    assert compression["target_ratio"] == 0.50
    assert compression["protect_first_n"] == 3
    assert compression["protect_last_n"] == 4
    assert compression["micro_compact"] is True
    assert compression["micro_compact_every_n_turns"] == 1
    assert compression["abort_on_summary_failure"] is False
    assert compression["in_place"] is True


def test_auxiliary_compression_keeps_only_auxiliary_provider_settings():
    auxiliary = DEFAULT_CONFIG["auxiliary"]["compression"]

    assert auxiliary["provider"] == "auto"
    assert auxiliary["model"] == ""
    assert auxiliary["timeout"] == 120
    assert "threshold" not in auxiliary
    assert "micro_compact" not in auxiliary
