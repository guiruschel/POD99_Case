#!/usr/bin/env bash
# Runs the pytest suite inside the AWS Glue Docker image (same Spark/Java
# version as the real job), instead of fighting local Java/Spark version
# mismatches on the host machine.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="amazon/aws-glue-libs:5.1.0"

docker run --rm \
  -v "$REPO_ROOT":/home/glue_user/workspace/ \
  -e DISABLE_SSL=true \
  -w /home/glue_user/workspace \
  "$IMAGE" \
  bash -c "pip install -q -r requirements-dev.txt && python3 -m pytest tests/ -v"
