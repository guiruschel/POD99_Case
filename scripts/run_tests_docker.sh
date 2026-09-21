#!/usr/bin/env bash
# Runs the pytest suite inside the AWS Glue Docker image (same Spark/Java
# version as the real job), instead of fighting local Java/Spark version
# mismatches on the host machine.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="amazon/aws-glue-libs:5.1.0"

# On Windows/git-bash (MSYS), the shell rewrites POSIX-looking paths (like the
# container-side /home/glue_user/workspace) into Windows paths before Docker
# ever sees them. Disabling that rewriting is required here.
export MSYS_NO_PATHCONV=1

# This image's ENTRYPOINT is already "bash -l", so args are passed straight
# to bash (as -c "..."), not wrapped in another bash -c. Container user is
# "hadoop", not "glue_user" (that was true for older Glue 4.0 images only).
docker run --rm \
  -v "$REPO_ROOT":/home/hadoop/workspace/ \
  -w /home/hadoop/workspace \
  "$IMAGE" \
  -c "pip install -q --user -r requirements-dev.txt && python3 -m pytest tests/ -v"
