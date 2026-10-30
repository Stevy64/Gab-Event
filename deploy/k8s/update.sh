#!/bin/sh
# Met à jour Gab Event sur le cluster déjà en place.
# gabevent-deploy         image GHCR (choix A, etape 4)
# gabevent-deploy local   image construite sur le VPS (choix B, etape 4)
# La migration passe avant le redémarrage. Si elle échoue, les pods en service restent.
set -eu
MODE=${1:-ghcr}
NS=gabevent
DIR=/srv/gabevent/deploy/k8s
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp "$DIR"/*.yaml "$WORK"/
if [ "$MODE" = local ]; then
  sed -i \
    -e 's|ghcr.io/stevy64/gabevent:main|docker.io/library/gabevent:1|g' \
    -e 's|imagePullPolicy: Always|imagePullPolicy: Never|g' \
    "$WORK"/*.yaml
fi
DIR=$WORK
kubectl apply -f "$DIR/redis.yaml" -f "$DIR/volumes.yaml"
kubectl -n "$NS" rollout status deployment/redis --timeout=180s
kubectl -n "$NS" delete job gabevent-migrate --ignore-not-found
kubectl apply -f "$DIR/migrate.yaml"
kubectl -n "$NS" wait --for=condition=complete job/gabevent-migrate --timeout=180s
kubectl apply -f "$DIR/web.yaml" -f "$DIR/celery.yaml"
kubectl -n "$NS" rollout restart deployment/gabevent-web deployment/gabevent-worker deployment/gabevent-beat
kubectl -n "$NS" rollout status deployment/gabevent-web --timeout=180s
kubectl -n "$NS" rollout status deployment/gabevent-worker --timeout=180s
kubectl -n "$NS" rollout status deployment/gabevent-beat --timeout=180s
