#!/bin/sh
# Met à jour Zanalyze sur le cluster déjà en place.
# zanalyze-deploy         image GHCR (choix A, etape 4)
# zanalyze-deploy local   image construite sur le VPS (choix B, etape 4)
# La migration passe avant le redémarrage. Si elle échoue, les pods en service restent.
set -eu
MODE=${1:-ghcr}
NS=zanalyze
DIR=/srv/zanalyze/deploy/k8s
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp "$DIR"/*.yaml "$WORK"/
if [ "$MODE" = local ]; then
  sed -i \
    -e 's|ghcr.io/stevy64/zanalyze:main|docker.io/library/zanalyze:1|g' \
    -e 's|imagePullPolicy: Always|imagePullPolicy: Never|g' \
    "$WORK"/*.yaml
fi
DIR=$WORK
kubectl apply -f "$DIR/redis.yaml" -f "$DIR/volumes.yaml"
kubectl -n "$NS" rollout status deployment/redis --timeout=180s
kubectl -n "$NS" delete job zanalyze-migrate --ignore-not-found
kubectl apply -f "$DIR/migrate.yaml"
kubectl -n "$NS" wait --for=condition=complete job/zanalyze-migrate --timeout=300s
kubectl apply -f "$DIR/moteur.yaml" -f "$DIR/web.yaml" -f "$DIR/worker.yaml"
kubectl -n "$NS" rollout restart deployment/zanalyze-moteur deployment/zanalyze-web deployment/zanalyze-worker
kubectl -n "$NS" rollout status deployment/zanalyze-moteur --timeout=300s
kubectl -n "$NS" rollout status deployment/zanalyze-web --timeout=300s
kubectl -n "$NS" rollout status deployment/zanalyze-worker --timeout=300s
