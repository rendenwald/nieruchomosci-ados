#!/usr/bin/env bash
# Verify Grafana provisioning for scraper monitoring dashboards.
#
# Usage:
#   GRAFANA_URL=http://localhost:3000 ./scripts/verify-grafana.sh
#
# Returns 0 if all checks pass, 1 otherwise.
set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        echo "  ✓ $name"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $name"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Grafana Verification ==="
echo "Target: $GRAFANA_URL"
echo ""

# 1. Health check — Grafana API responds
check "Grafana health API" \
    "curl -sf '$GRAFANA_URL/api/health' | jq -e '.database == \"ok\"'"

# 2. Datasource check — Prometheus datasource exists
check "Prometheus datasource provisioned" \
    "curl -sf '$GRAFANA_URL/api/datasources' | jq -e '.[] | select(.name == \"Prometheus\")'"

# 3. Dashboard check — Scrapers Overview exists
check "Scrapers Overview dashboard" \
    "curl -sf '$GRAFANA_URL/api/search?query=Scrapers%20Overview' | jq -e 'length > 0'"

# 4. Anonymous access check — no auth required
check "Anonymous access enabled" \
    "curl -sf -o /dev/null -w '%{http_code}' '$GRAFANA_URL/api/frontend/settings' | grep -q '200'"

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
