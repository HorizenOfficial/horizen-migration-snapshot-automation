#!/usr/bin/env bash
set -eEuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &>/dev/null && pwd)"

echo -e "\n\033[1m=== Cleaning all artifacts and data ===\033[0m"

# Making sure the script is not being run as root
CURRENT_USER_ID="$(id -u)"
CURRENT_GROUP_ID="$(id -g)"
if [ "${CURRENT_USER_ID}" == 0 ] || [ "${CURRENT_GROUP_ID}" == 0 ]; then
  fn_die "Error: This script should not be run as root. Exiting..."
fi

docker compose down --remove-orphans --volumes --rmi all
rm -r /path/to/cloned/repo
docker system prune --all --force --volumes # this will remove all docker images of non-running containers, also images unrelated to the migration
docker buildx prune -f

echo -e "\n\033[1m=== All nuked ===\033[0m"
