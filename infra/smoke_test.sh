#!/usr/bin/env bash
# StrataBI post-apply smoke test.
# Usage: ./smoke_test.sh <name_prefix> <region>
# Requires: awscli configured with read access to the install account.
set -uo pipefail

PREFIX="${1:-stratabi}"
REGION="${2:-us-east-1}"
fail=0

ok()   { echo "  OK   $1"; }
bad()  { echo "  FAIL $1"; fail=1; }

echo "StrataBI smoke test — prefix=${PREFIX} region=${REGION}"

echo "[ALB]"
alb_dns=$(aws elbv2 describe-load-balancers --names "${PREFIX}-alb" \
  --region "$REGION" --query 'LoadBalancers[0].DNSName' --output text 2>/dev/null)
[ -n "$alb_dns" ] && [ "$alb_dns" != "None" ] && ok "ALB ${PREFIX}-alb (${alb_dns})" || bad "ALB ${PREFIX}-alb not found"

echo "[ECS]"
running=$(aws ecs describe-services --cluster "${PREFIX}-cluster" \
  --services "${PREFIX}-service" --region "$REGION" \
  --query 'services[0].runningCount' --output text 2>/dev/null)
[ -n "$running" ] && [ "$running" != "None" ] && ok "ECS service runningCount=${running}" || bad "ECS service not found"

echo "[Lambda]"
for fn in "${PREFIX}-athena-async" "${PREFIX}-status-writer"; do
  aws lambda get-function --function-name "$fn" --region "$REGION" >/dev/null 2>&1 \
    && ok "lambda $fn" || bad "lambda $fn missing"
done

echo "[DynamoDB]"
for t in "${PREFIX}_tile_status" "${PREFIX}_module_registry" "${PREFIX}_source_registry" \
         "${PREFIX}-dashboard-favorites" "${PREFIX}-dashboard-pinned" "${PREFIX}-dashboard-recents"; do
  aws dynamodb describe-table --table-name "$t" --region "$REGION" >/dev/null 2>&1 \
    && ok "table $t" || bad "table $t missing"
done

echo "[S3]"
acct=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
bucket="${PREFIX}-system-${acct}"
aws s3api head-bucket --bucket "$bucket" --region "$REGION" >/dev/null 2>&1 \
  && ok "bucket $bucket" || bad "bucket $bucket missing"

echo
[ "$fail" -eq 0 ] && echo "SMOKE TEST PASSED" || { echo "SMOKE TEST FAILED"; exit 1; }
