#!/usr/bin/env bash
# Lint and unit-test the alert rules with the same promtool Prometheus runs.
set -euo pipefail
cd "$(dirname "$0")"
IMAGE=prom/prometheus:v3.5.0   # keep in step with docker/monitoring/docker-compose.yml
docker run --rm --entrypoint promtool -v "$PWD:/m:ro" -w /m "$IMAGE" check rules rules/*.yml
docker run --rm --entrypoint promtool -v "$PWD:/m:ro" -w /m "$IMAGE" test rules tests/*.yml
