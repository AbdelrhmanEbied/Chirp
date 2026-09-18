#!/bin/bash
set -euo pipefail

REGION="us-east-1"
CLUSTER="chirp-prod"
NAMESPACE="chirp-prod"
ECR_REPO="chirp-prod"

log() { echo -e "\033[1;36m==> $1\033[0m"; }

log "Step 1: Creating Terraform state bucket"
aws s3 mb s3://chirp-terraform-state --region "$REGION" 2>/dev/null || true
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST 2>/dev/null || true

log "Step 2: Generating secrets"
export TF_VAR_jwt_secret=$(openssl rand -hex 32)
export TF_VAR_db_password=$(openssl rand -hex 16)
echo "JWT_SECRET=$TF_VAR_jwt_secret" > .env.secrets
echo "DB_PASSWORD=$TF_VAR_db_password" >> .env.secrets
chmod 600 .env.secrets
log "Secrets saved to .env.secrets"

log "Step 3: Deploying infrastructure with Terraform"
cd infra/terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
cd ../..

log "Step 4: Configuring kubectl"
aws eks update-kubeconfig --name "$CLUSTER" --region "$REGION"

log "Step 5: Creating K8s secrets"
kubectl create namespace "$NAMESPACE" 2>/dev/null || true
kubectl delete secret chirp-secrets -n "$NAMESPACE" 2>/dev/null || true

ECR_URL=$(cd infra/terraform && terraform output -raw ecr_repository_url)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

kubectl create secret generic chirp-secrets \
  --from-literal=JWT_SECRET="$TF_VAR_jwt_secret" \
  --from-literal=POSTGRES_PASSWORD="$TF_VAR_db_password" \
  --from-literal=DATABASE_URL_AUTH="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_auth" \
  --from-literal=DATABASE_URL_USER="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_user" \
  --from-literal=DATABASE_URL_POST="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_post" \
  --from-literal=DATABASE_URL_GRAPH="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_graph" \
  --from-literal=DATABASE_URL_TIMELINE="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_timeline" \
  --from-literal=DATABASE_URL_SEARCH="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_search" \
  --from-literal=DATABASE_URL_NOTIFICATION="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_notification" \
  --from-literal=DATABASE_URL_MESSAGING="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_messaging" \
  --from-literal=DATABASE_URL_MEDIA="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_media" \
  --from-literal=DATABASE_URL_MODERATION="postgresql+asyncpg://chirp_admin:${TF_VAR_db_password}@$(cd infra/terraform && terraform output -raw rds_host):$(cd infra/terraform && terraform output -raw rds_port)/chirp_moderation" \
  --from-literal=REDIS_URL="redis://$(cd infra/terraform && terraform output -raw redis_endpoint):$(cd infra/terraform && terraform output -raw redis_port)/0" \
  --from-literal=EVENT_BUS_URL="redis://$(cd infra/terraform && terraform output -raw redis_endpoint):$(cd infra/terraform && terraform output -raw redis_port)/1" \
  --from-literal=S3_BUCKET="$ECR_REPO-media" \
  -n "$NAMESPACE"

log "Step 6: Installing AWS Load Balancer Controller"
helm repo add eks https://aws.github.io/eks-charts 2>/dev/null || true
helm repo update
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName="$CLUSTER" \
  --set serviceAccount.create=true \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="" \
  --wait

log "Step 7: Building and pushing Docker images"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

for svc in gateway auth user post graph timeline search notification messaging media moderation; do
  log "  Building $svc..."
  docker build -t "$ECR_URL-$svc:latest" -t "$ECR_URL-$svc:${GITHUB_SHA:-latest}" -f services/$svc/Dockerfile .
  docker push "$ECR_URL-$svc:latest"
  docker push "$ECR_URL-${svc}:${GITHUB_SHA:-latest}"
done

log "Step 8: Running migrations"
for svc in auth user post graph timeline search notification messaging media moderation; do
  log "  Migrating $svc..."
  kubectl delete job "$svc-migrate" -n "$NAMESPACE" --ignore-not-found
  kubectl apply -f k8s/services/$svc/job-migrate.yaml
  kubectl wait --for=condition=complete "job/$svc-migrate" -n "$NAMESPACE" --timeout=120s
done

log "Step 9: Deploying services"
kubectl apply -f k8s/base/
kubectl apply -f k8s/services/
kubectl apply -f k8s/ingress/

log "Step 10: Waiting for rollout"
for svc in gateway auth user post graph timeline search notification messaging media moderation; do
  kubectl rollout status "deployment/$svc" -n "$NAMESPACE" --timeout=300s &
done
wait

log "Step 11: Deploying frontend"
cd web && npm run build
FRONTEND_BUCKET=$(cd ../infra/terraform && terraform output -raw s3_frontend_bucket)
CF_ID=$(cd ../infra/terraform && terraform output -raw cloudfront_distribution_id)
aws s3 sync dist/ "s3://$FRONTEND_BUCKET/"
aws cloudfront create-invalidation --distribution-id "$CF_ID" --paths "/*"
cd ..

log "============================================"
log "DEPLOYMENT COMPLETE"
log "============================================"
log ""
log "API Gateway URL:"
ALB_DNS=$(kubectl get ingress gateway-ingress -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "  http://$ALB_DNS"
log ""
log "Frontend URL:"
CF_DOMAIN=$(cd infra/terraform && terraform output -raw cloudfront_domain)
echo "  https://$CF_DOMAIN"
log ""
log "To check pod status:"
echo "  kubectl get pods -n $NAMESPACE"
log ""
log "To check logs:"
echo "  kubectl logs -f deployment/gateway -n $NAMESPACE"
log ""
log "To run load tests:"
echo "  k6 run --vus 50 --duration 5m --env BASE_URL=http://$ALB_DNS loadtest/critical_path.js"
