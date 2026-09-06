#!/usr/bin/env bash
# Bring the disposable peer gateway up or down.
#
# `up` generates dockers/.env with a RANDOM admin password on first use. The
# password is never printed, never passed on a command line, and never leaves
# that file — which is gitignored. It is a throwaway credential for a
# throwaway gateway; nothing else should ever hold it.
#
# `down` removes the container AND the volume. That is the point: this rig
# exists for one validation run.
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE=.env
URL=http://localhost:8099

usage() { echo "usage: $0 {up|down|status}" >&2; exit 2; }
[ $# -eq 1 ] || usage

case "$1" in
  up)
    if [ ! -f "$ENV_FILE" ]; then
      # 32 URL-safe characters from the kernel's CSPRNG. Written with a
      # restrictive umask so it is 0600 from the moment it exists rather than
      # after a chmod that a crash could skip.
      ( umask 077
        printf 'GATEWAY_ADMIN_USERNAME=admin\nGATEWAY_ADMIN_PASSWORD=%s\n' \
          "$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 32)" > "$ENV_FILE" )
      echo "generated $ENV_FILE (0600, not printed, gitignored)"
    fi
    docker compose up -d
    echo -n "waiting for the peer gateway to report RUNNING"
    for _ in $(seq 1 90); do
      state=$(curl -s -m 5 "$URL/StatusPing" 2>/dev/null || true)
      case "$state" in
        *RUNNING*) echo; echo "peer gateway RUNNING at $URL"; exit 0;;
      esac
      echo -n .
      sleep 5
    done
    echo
    echo "peer gateway did not reach RUNNING in 450s; last: ${state:-<no answer>}" >&2
    exit 1
    ;;
  down)
    # -v is the whole point: the volume goes with the container. Without it a
    # ~1 GB data volume survives every run and the disk fills quietly.
    docker compose down -v
    rm -f "$ENV_FILE"
    echo "peer gateway and its volume removed; $ENV_FILE deleted"
    ;;
  status)
    docker compose ps
    curl -s -m 5 "$URL/StatusPing" 2>/dev/null || echo "(no answer from $URL)"
    ;;
  *) usage;;
esac
