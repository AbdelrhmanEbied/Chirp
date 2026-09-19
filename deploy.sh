#!/bin/bash
set -euo pipefail

REGION="us-east-1"
CLUSTER="chirp-prod"
NAMESPACE="chirp-prod"

log() { echo -e "\033[1;36m==> $1\033[0m"; }

if [ "${1:-}" = "--destroy" ]; then
  log "DESTROYING ALL INFRASTRUCTURE"
  cd infra/terraform
  terraform destroy -auto-approve
  cd ../..
  log "Infrastructure destroyed. Run ./deploy.sh to redeploy."
  exit 0
fi

if ! command -v aws &>/dev/null; then
  log "Installing AWS CLI"
  curl "https://awscli.amazonaws.com/awscli-exe-linux-x64.zip" -o "awscliv2.zip"
  unzip -q awscliv2.zip
  sudo ./aws/install
  rm -rf aws awscliv2.zip
fi

if ! command -v terraform &>/dev/null; then
  log "Installing Terraform"
  sudo apt-get update -qq && sudo apt-get install -y -qq gnupg software-properties-common curl
  curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
  sudo apt-get update -qq && sudo apt-get install -y -qq terraform
fi

if ! command -v kubectl &>/dev/null; then
  log "Installing kubectl"
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
  rm kubectl
fi

if ! command -v helm &>/dev/null; then
  log "Installing Helm"
  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

if ! command -v k6 &>/dev/null; then
  log "Installing k6"
  K6_VERSION=$(curl -s https://api.github.com/repos/grafana/k6/releases/latest | grep tag_name | cut -d '"' -f 4)
  curl -sL "https://github.com/grafana/k6/releases/download/${K6_VERSION}/k6-${K6_VERSION}-linux-amd64.tar.gz" -o /tmp/k6.tar.gz
  tar -xzf /tmp/k6.tar.gz -C /tmp
  sudo mv "/tmp/k6-${K6_VERSION}-linux-amd64/k6" /usr/local/bin/k6
  rm -rf /tmp/k6*
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TF_BUCKET="chirp-terraform-${ACCOUNT_ID}"

INFRA_READY=false
if aws eks describe-cluster --name "$CLUSTER" --region "$REGION" &>/dev/null; then
  INFRA_READY=true
  log "EKS cluster $CLUSTER already exists"
fi

if [ "$INFRA_READY" = false ]; then
  log "Step 1: Checking Terraform state bucket"
  if ! aws s3api head-bucket --bucket "$TF_BUCKET" 2>/dev/null; then
    log "Creating Terraform state bucket: $TF_BUCKET"
    aws s3 mb "s3://$TF_BUCKET" --region "$REGION"
  else
    log "Bucket $TF_BUCKET already exists"
  fi

  log "Step 2: Generating secrets"
  export TF_VAR_jwt_secret=$(openssl rand -hex 32)
  export TF_VAR_db_password=$(openssl rand -hex 16)
  echo "JWT_SECRET=$TF_VAR_jwt_secret" > .env.secrets
  echo "DB_PASSWORD=$TF_VAR_db_password" >> .env.secrets
  chmod 600 .env.secrets
  log "Secrets saved to .env.secrets"

  log "Step 3: Deploying infrastructure with Terraform"
  cd infra/terraform
  terraform init -backend-config="bucket=$TF_BUCKET"
  terraform apply -auto-approve
  cd ../..
else
  log "Loading existing secrets from .env.secrets"
  if [ ! -f .env.secrets ]; then
    log "ERROR: .env.secrets not found. Run ./deploy.sh without --destroy first."
    exit 1
  fi
  source .env.secrets
  export TF_VAR_jwt_secret="$JWT_SECRET"
  export TF_VAR_db_password="$DB_PASSWORD"
fi

log "Step 4: Configuring kubectl"
aws eks update-kubeconfig --name "$CLUSTER" --region "$REGION"

log "Step 5: Granting EKS access"
aws eks create-access-entry --cluster-name "$CLUSTER" --principal-arn "arn:aws:iam::${ACCOUNT_ID}:user/abdo-admin" --type STANDARD --region "$REGION" 2>/dev/null || true
aws eks associate-access-policy --cluster-name "$CLUSTER" --principal-arn "arn:aws:iam::${ACCOUNT_ID}:user/abdo-admin" --policy-arn "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy" --access-scope type=cluster --region "$REGION" 2>/dev/null || true

log "Step 6: Creating K8s namespace and secrets"
kubectl create namespace "$NAMESPACE" 2>/dev/null || true
kubectl delete secret chirp-secrets -n "$NAMESPACE" 2>/dev/null || true

ECR_URL=$(cd infra/terraform && terraform output -raw ecr_repository_url)

kubectl create secret generic chirp-secrets \
  --from-literal=JWT_SECRET="$TF_VAR_jwt_secret" \
  --from-literal=POSTGRES_PASSWORD="$TF_VAR_db_password" \
  --from-literal=RDS_HOST="$(cd infra/terraform && terraform output -raw rds_host)" \
  --from-literal=RDS_PORT="$(cd infra/terraform && terraform output -raw rds_port)" \
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
  --from-literal=S3_BUCKET="$(cd infra/terraform && terraform output -raw s3_media_bucket)" \
  -n "$NAMESPACE"

log "Step 7: Creating service databases"
kubectl delete job init-db -n "$NAMESPACE" 2>/dev/null || true
kubectl wait --for=delete pod -l app=init-db -n "$NAMESPACE" --timeout=30s 2>/dev/null || true
kubectl apply -f k8s/base/init-db-job.yaml
kubectl wait --for=condition=complete job/init-db -n "$NAMESPACE" --timeout=180s
log "Databases created"

log "Step 8: Installing AWS Load Balancer Controller"
helm repo add eks https://aws.github.io/eks-charts 2>/dev/null || true
helm repo update
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName="$CLUSTER" \
  --set serviceAccount.create=true \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="" \
  --force \
  --wait

log "Step 9: Building and pushing Docker images"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

log "  Building base image..."
docker build -t chirp-base:latest -f Dockerfile.base .
docker tag chirp-base:latest "$ECR_URL:base"
docker push "$ECR_URL:base"

for svc in gateway auth user post graph timeline search notification messaging media moderation; do
  log "  Building $svc..."
  docker build -t "$ECR_URL:${svc}-latest" -f services/$svc/Dockerfile .
  docker push "$ECR_URL:${svc}-latest"
done

log "Step 10: Applying K8s base resources"
kubectl apply -f k8s/base/

log "Step 11: Fixing image references"
for svc in gateway auth user post graph timeline search notification messaging media moderation; do
  sed -i "s|image: chirp/${svc}:latest|image: ${ECR_URL}:${svc}-latest|g" k8s/services/$svc/deployment.yaml k8s/services/$svc/job-migrate.yaml 2>/dev/null || true
done

log "Step 12: Running migrations"
for svc in auth user post graph timeline search notification messaging media moderation; do
  log "  Migrating $svc..."
  kubectl delete job "$svc-migrate" -n "$NAMESPACE" --ignore-not-found
  kubectl apply -f k8s/services/$svc/job-migrate.yaml
  kubectl wait --for=condition=complete "job/$svc-migrate" -n "$NAMESPACE" --timeout=120s
done

log "Step 13: Deploying services"
kubectl apply -f k8s/services/
kubectl apply -f k8s/ingress/

log "Step 14: Waiting for rollout"
for svc in gateway auth user post graph timeline search notification messaging media moderation; do
  kubectl rollout status "deployment/$svc" -n "$NAMESPACE" --timeout=300s &
done
wait

log "Step 15: Deploying monitoring (Prometheus + Grafana)"
kubectl apply -f k8s/monitoring/prometheus.yaml
kubectl apply -f k8s/monitoring/grafana.yaml
kubectl apply -f k8s/monitoring/ingress.yaml
kubectl rollout status deployment/prometheus -n monitoring --timeout=120s &
kubectl rollout status deployment/grafana -n monitoring --timeout=120s &
wait

log "Step 16: Deploying frontend"
cd web && npm run build
FRONTEND_BUCKET=$(cd ../infra/terraform && terraform output -raw s3_frontend_bucket)
CF_ID=$(cd ../infra/terraform && terraform output -raw cloudfront_distribution_id)
aws s3 sync dist/ "s3://$FRONTEND_BUCKET/"
aws cloudfront create-invalidation --distribution-id "$CF_ID" --paths "/*"
cd ..

log "============================================"
log "DEPLOYMENT COMPLETE"
log "============================================"
ALB_DNS=$(kubectl get ingress gateway-ingress -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
CF_DOMAIN=$(cd infra/terraform && terraform output -raw cloudfront_domain)
echo ""
echo "  API:     http://$ALB_DNS"
echo "  Frontend: https://$CF_DOMAIN"
echo ""
echo "  kubectl get pods -n $NAMESPACE"
echo "  kubectl logs -f deployment/gateway -n $NAMESPACE"
