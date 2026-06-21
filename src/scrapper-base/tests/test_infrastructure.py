"""Tests for infrastructure configuration files (docker, prometheus, alertmanager).

These tests validate that config files are parseable and have the expected
structure. They do not require Docker or any external services.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # src/scrapper-base/tests/ → repo root


class TestAlertRules:
    """docker/prometheus/alert-rules.yml is valid."""

    RULES_PATH = REPO_ROOT / "docker" / "prometheus" / "alert-rules.yml"

    def test_file_exists(self):
        """alert-rules.yml exists and is non-empty."""
        assert self.RULES_PATH.exists()
        assert self.RULES_PATH.stat().st_size > 0

    def test_contains_groups(self):
        """The YAML has a 'groups' key."""
        content = self.RULES_PATH.read_text()
        assert "groups:" in content

    def test_contains_expected_alerts(self):
        """Both expected alert rules are defined."""
        content = self.RULES_PATH.read_text()
        assert "ScraperHighErrorRate" in content
        assert "ScraperNotRunning" in content
        assert "scrape_errors_total" in content
        assert "scraper_last_run_timestamp" in content

    def test_basic_yaml_structure(self):
        """Minimal YAML structure check — groups and alert definitions present."""
        content = self.RULES_PATH.read_text()
        # Find the first groups: line (after comments)
        assert "groups:" in content
        # At least one rule with - alert: name
        rule_count = len(re.findall(r"^\s+- alert:", content, re.MULTILINE))
        assert rule_count >= 2, f"Expected ≥2 alert rules, found {rule_count}"


class TestPrometheusConfig:
    """docker/prometheus/prometheus.yml is valid."""

    CONFIG_PATH = REPO_ROOT / "docker" / "prometheus" / "prometheus.yml"

    def test_file_exists(self):
        """prometheus.yml exists and is non-empty."""
        assert self.CONFIG_PATH.exists()
        assert self.CONFIG_PATH.stat().st_size > 0

    def test_contains_required_keys(self):
        """Basic structure keys present."""
        content = self.CONFIG_PATH.read_text()
        assert "scrape_configs:" in content
        assert "rule_files:" in content
        assert "pushgateway" in content

    def test_refers_to_rules(self):
        """rule_files references alert-rules.yml."""
        content = self.CONFIG_PATH.read_text()
        assert "alert-rules.yml" in content


class TestAlertmanagerConfig:
    """docker/alertmanager/alertmanager.yml is valid."""

    CONFIG_PATH = REPO_ROOT / "docker" / "alertmanager" / "alertmanager.yml"

    def test_file_exists(self):
        """alertmanager.yml exists and is non-empty."""
        assert self.CONFIG_PATH.exists()
        assert self.CONFIG_PATH.stat().st_size > 0

    def test_contains_receiver(self):
        """Has at least one receiver defined."""
        content = self.CONFIG_PATH.read_text()
        assert "receivers:" in content
        assert "console" in content

    def test_has_route(self):
        """Route configuration is present."""
        content = self.CONFIG_PATH.read_text()
        assert "route:" in content
        assert "receiver:" in content
