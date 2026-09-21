#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"

make -C "$repo_dir" build/image_benchmark

printf 'Executável pronto: %s\n' "$repo_dir/build/image_benchmark"
