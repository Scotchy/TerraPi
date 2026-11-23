#!/usr/bin/env bash
set -euo pipefail
out=dist/release
bash deploy/ci/package.sh "$out"
registry="ghcr.io/${GITHUB_REPOSITORY,,}"
printf '%s' "$REGISTRY_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin
trap 'docker logout ghcr.io >/dev/null' EXIT
docker load -i "$RUNNER_TEMP/tested-images.tgz"
for component in frontend notifier monitoring; do
    image="$registry/$component:$GITHUB_SHA"
    docker tag "terrapi-ci/$component:test" "$image"
    docker push "$image"
    digest=$(docker image inspect "$image" --format '{{index .RepoDigests 0}}')
    printf '%s\n' "$digest" > "$RUNNER_TEMP/$component.digest"
done
python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
out = Path("dist/release")
tmp = Path(os.environ["RUNNER_TEMP"])
release = {name: (tmp / (name + ".digest")).read_text().strip() for name in ("frontend", "notifier", "monitoring")}
release.update(revision=os.environ["GITHUB_SHA"], broker=Path("deploy/vps/broker-image").read_text().strip(),
               controller_sha256=hashlib.sha256((out / "controller.tgz").read_bytes()).hexdigest())
(out / "release.json").write_text(json.dumps(release))
PY
