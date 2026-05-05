#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

image="${CC_EXTRACTOR_SMOKE_IMAGE:-cc-extractor-patch-smoke:local}"
platform="${DOCKER_PLATFORM:-linux/amd64}"
workspace="${CC_EXTRACTOR_DOCKER_WORKSPACE:-/work/.cc-extractor/docker-linux}"

if [ "$#" -eq 0 ]; then
  set -- --all --max-versions 10 --run-smoke --smoke-timeout 60
fi

mkdir -p "$repo_root/.cc-extractor/docker-linux" "$repo_root/reports/patch-compat"

docker build \
  --platform "$platform" \
  -f "$repo_root/docker/patch-smoke/Dockerfile" \
  -t "$image" \
  "$repo_root"

docker run --rm \
  --platform "$platform" \
  --user "$(id -u):$(id -g)" \
  -e CC_EXTRACTOR_WORKSPACE="$workspace" \
  -e HOME=/tmp/cc-extractor-home \
  -v "$repo_root:/work" \
  "$image" \
  "$@"
