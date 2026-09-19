#!/bin/bash
set -uo pipefail

REGION="us-east-1"
CLUSTER="chirp-prod"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)

ok() { echo -e "\033[1;32m  ✓ $1\033[0m"; }
skip() { echo -e "\033[1;33m  - $1 (not found, skipping)\033[0m"; }
fail() { echo -e "\033[1;31m  ✗ $1\033[0m"; }

echo "=== EKS Nodegroup ==="
NG=$(aws eks list-nodegroups --cluster-name "$CLUSTER" --region "$REGION" --query nodegroups[0] --output text 2>/dev/null || echo "None")
if [ -n "$NG" ] && [ "$NG" != "None" ]; then
  aws eks delete-nodegroup --cluster-name "$CLUSTER" --nodegroup-name "$NG" --region "$REGION" 2>/dev/null && ok "Deleting $NG..." || fail "Failed to delete nodegroup"
  aws eks wait nodegroup-deleted --cluster-name "$CLUSTER" --nodegroup-name "$NG" --region "$REGION" 2>/dev/null && ok "Nodegroup deleted" || fail "Wait failed"
else
  skip "No nodegroup"
fi

echo "=== EKS Cluster ==="
if aws eks describe-cluster --name "$CLUSTER" --region "$REGION" &>/dev/null; then
  aws eks delete-cluster --name "$CLUSTER" --region "$REGION" 2>/dev/null && ok "Deleting cluster..." || fail "Failed"
  aws eks wait cluster-deleted --name "$CLUSTER" --region "$REGION" 2>/dev/null && ok "Cluster deleted" || fail "Wait failed"
else
  skip "No cluster"
fi

echo "=== RDS ==="
if aws rds describe-db-instances --db-instance-identifier chirp-prod --region "$REGION" &>/dev/null; then
  aws rds delete-db-instance --db-instance-identifier chirp-prod --skip-final-snapshot --region "$REGION" 2>/dev/null && ok "Deleting RDS..." || fail "Failed"
  aws rds wait db-instance-deleted --db-instance-identifier chirp-prod --region "$REGION" 2>/dev/null && ok "RDS deleted" || fail "Wait failed"
else
  skip "No RDS"
fi

echo "=== ElastiCache ==="
if aws elasticache describe-replication-groups --replication-group-id chirp-prod --region "$REGION" --query 'ReplicationGroups[0].ReplicationGroupId' --output text 2>/dev/null | grep -q chirp-prod; then
  aws elasticache delete-replication-group --replication-group-id chirp-prod --region "$REGION" 2>/dev/null && ok "Deleting Redis..." || fail "Failed"
  aws elasticache wait replication-group-deleted --replication-group-id chirp-prod --region "$REGION" 2>/dev/null && ok "Redis deleted" || fail "Wait failed"
else
  skip "No Redis"
fi

echo "=== Subnet Groups ==="
aws rds delete-db-subnet-group --db-subnet-group-name chirp-prod --region "$REGION" 2>/dev/null && ok "RDS subnet group deleted" || skip "No RDS subnet group"
aws elasticache delete-cache-subnet-group --cache-subnet-group-name chirp-prod --region "$REGION" 2>/dev/null && ok "Cache subnet group deleted" || skip "No cache subnet group"

echo "=== S3 Buckets ==="
for BUCKET in chirp-prod-frontend-${ACCOUNT_ID} chirp-prod-media-${ACCOUNT_ID}; do
  if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    aws s3 rb "s3://$BUCKET" --force --region "$REGION" 2>/dev/null && ok "$BUCKET deleted" || fail "Failed to delete $BUCKET"
  else
    skip "$BUCKET"
  fi
done

echo "=== ECR ==="
if aws ecr describe-repositories --repository-names chirp-prod --region "$REGION" &>/dev/null; then
  aws ecr delete-repository --repository-name chirp-prod --force --region "$REGION" 2>/dev/null && ok "ECR deleted" || fail "Failed"
else
  skip "No ECR"
fi

echo "=== CloudFront ==="
CF_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='chirp frontend CDN'].Id" --output text 2>/dev/null || echo "None")
if [ -n "$CF_ID" ] && [ "$CF_ID" != "None" ]; then
  ETAG=$(aws cloudfront get-distribution-config --id "$CF_ID" --query 'ETag' --output text 2>/dev/null || echo "")
  if [ -n "$ETAG" ]; then
    # Must disable before deleting
    DIST_CONFIG=$(aws cloudfront get-distribution-config --id "$CF_ID" --query 'DistributionConfig' --output json 2>/dev/null)
    DISABLED_CONFIG=$(echo "$DIST_CONFIG" | python3 -c "import sys,json; c=json.load(sys.stdin); c['Enabled']=False; print(json.dumps(c))" 2>/dev/null || echo "")
    if [ -n "$DISABLED_CONFIG" ]; then
      aws cloudfront update-distribution --id "$CF_ID" --if-match "$ETAG" --distribution-config "$DISABLED_CONFIG" &>/dev/null && ok "Disabling CloudFront..." || skip "CloudFront already disabled"
      echo "  Waiting 60s for CloudFront to disable..."
      sleep 60
    fi
    ETAG2=$(aws cloudfront get-distribution-config --id "$CF_ID" --query 'ETag' --output text 2>/dev/null || echo "")
    if [ -n "$ETAG2" ]; then
      aws cloudfront delete-distribution --id "$CF_ID" --if-match "$ETAG2" 2>/dev/null && ok "CloudFront deleted" || fail "Failed"
    fi
  fi
else
  skip "No CloudFront"
fi

echo "=== IAM ==="
for ROLE in chirp-prod-github-actions chirp-prod-media; do
  if aws iam get-role --role-name "$ROLE" &>/dev/null; then
    # Detach all managed policies
    POLICIES=$(aws iam list-attached-role-policies --role-name "$ROLE" --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null || echo "")
    for ARN in $POLICIES; do
      aws iam detach-role-policy --role-name "$ROLE" --policy-arn "$ARN" 2>/dev/null || true
    done
    # Delete all inline policies
    INLINE=$(aws iam list-role-policies --role-name "$ROLE" --query 'PolicyNames[]' --output text 2>/dev/null || echo "")
    for NAME in $INLINE; do
      aws iam delete-role-policy --role-name "$ROLE" --policy-name "$NAME" 2>/dev/null || true
    done
    aws iam delete-role --role-name "$ROLE" 2>/dev/null && ok "IAM role $ROLE deleted" || fail "Failed to delete $ROLE"
  else
    skip "IAM role $ROLE"
  fi
done

echo "=== CloudWatch Logs ==="
LOG_GROUPS=$(aws logs describe-log-groups --log-group-name-prefix "/aws/eks/chirp-prod" --query 'logGroups[].logGroupName' --output text 2>/dev/null || echo "")
for LG in $LOG_GROUPS; do
  aws logs delete-log-group --log-group-name "$LG" 2>/dev/null && ok "Deleted log group: $LG" || fail "Failed to delete $LG"
done
[ -z "$LOG_GROUPS" ] && skip "No CloudWatch log groups"

echo "=== KMS ==="
KMS_ID=$(aws kms list-keys --query "Keys[?contains(Aliases[0].AliasName, 'alias/eks/chirp-prod')].KeyId" --output text 2>/dev/null || echo "None")
if [ -n "$KMS_ID" ] && [ "$KMS_ID" != "None" ] && [ "$KMS_ID" != "" ]; then
  aws kms schedule-key-deletion --key-id "$KMS_ID" --pending-window-in-days 7 2>/dev/null && ok "KMS key scheduled for deletion" || skip "KMS key already pending deletion"
else
  skip "No KMS key"
fi

echo "=== State Bucket ==="
if aws s3api head-bucket --bucket "chirp-terraform-${ACCOUNT_ID}" 2>/dev/null; then
  aws s3 rb "s3://chirp-terraform-${ACCOUNT_ID}" --force --region "$REGION" 2>/dev/null && ok "State bucket deleted" || fail "Failed"
else
  skip "No state bucket"
fi

echo "=== Local Cleanup ==="
rm -rf .terraform .terraform.lock.hcl infra/terraform/.terraform infra/terraform/.terraform.lock.hcl 2>/dev/null
ok "Local terraform files cleaned"

echo ""
echo "============================================"
echo "  ALL RESOURCES DELETED"
echo "  Run: ./deploy.sh"
echo "============================================"
