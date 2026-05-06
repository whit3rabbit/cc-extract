#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

image="${CCSILO_SMOKE_IMAGE:-ccsilo-patch-smoke:local}"
platform="${DOCKER_PLATFORM:-linux/amd64}"
workspace="${CCSILO_DOCKER_WORKSPACE:-/work/.ccsilo/docker-linux}"

if [ "$#" -eq 0 ]; then
  set -- --all --max-versions 10 --run-smoke --smoke-timeout 60
fi

mkdir -p "$repo_root/.ccsilo/docker-linux" "$repo_root/reports/patch-compat"

docker build \
  --platform "$platform" \
  -f "$repo_root/docker/patch-smoke/Dockerfile" \
  -t "$image" \
  "$repo_root"

docker run --rm \
  --platform "$platform" \
  --user "$(id -u):$(id -g)" \
  -e CCSILO_WORKSPACE="$workspace" \
  -e HOME=/tmp/ccsilo-home \
  -v "$repo_root:/work" \
  "$image" \
  "$@"
