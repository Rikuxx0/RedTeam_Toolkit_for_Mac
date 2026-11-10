#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$project_root"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  printf 'This installer requires native macOS arm64.\n' >&2
  exit 3
fi

if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3.10 or newer is required before running install.sh.\n' >&2
  exit 3
fi
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  printf 'Python 3.10 or newer is required before running install.sh.\n' >&2
  exit 3
fi

exec python3 -m installer.main "$@"
