# CI/CD on AWS from scratch (ECR, EKS, GitHub Actions, CloudWatch)

This guide walks through running the same Docker image you built locally in a **continuous pipeline**: tests and image build in **GitHub Actions**, image storage in **Amazon ECR**, runtime on **Amazon EKS**, and **Amazon CloudWatch Logs** for observability.

It assumes you only have a new **AWS account** and a **GitHub** account. You will use a computer with a terminal (macOS, Linux, or Windows with WSL).

---

## 1. What you are building

| Piece | Role |
|--------|------|
| **GitHub Actions** | On each push to `main` (or `master`): run tests, build the Docker image, push to ECR, apply Kubernetes manifests, wait for rollout. |
| **Amazon ECR** | Private container registry for your image. |
| **Amazon EKS** | Managed Kubernetes cluster that runs your pods. |
| **AWS Secrets Manager** | Stores `OPENAI_API_KEY` as JSON (production path used by this app). |
| **CloudWatch Logs** | Log storage: JSON logs always go to **stdout** in the pod; you can also enable **direct** delivery via the app’s optional CloudWatch handler (`watchtower`). |

Workflow file in this repo: `.github/workflows/deploy.yml`.

---

## 2. AWS Free Tier and real costs (read this first)

The **AWS Free Tier** (first 12 months for many services) helps with **EC2**, **Lambda**, **S3**, and other services, but:

- **Amazon EKS charges for the control plane** about **$0.10 per hour** (roughly **$73 per month** per cluster), and that is **not** covered by the classic “free tier” in the same way as, for example, **750 hours of `t2.micro` EC2**. You also pay for **worker nodes** (EC2 or Fargate) that run your pods.
- **Amazon CloudWatch Logs** includes a small monthly allowance for ingestion and storage; for a demo workload, costs are usually low if you avoid huge log volume and long retention.

So: an **“only Free Tier”** account is enough to *open* AWS, but **running EKS is not free**. Budget a small monthly amount or use **AWS credits** (education programs, startup credits). If you must stay near zero cost, you would need a different architecture (for example **ECS Fargate** or a single **EC2** instance); this repository is wired for **EKS**, so the steps below match that.

---

## 3. Prerequisites checklist

1. **AWS account** with a payment method (required for most services).
2. **Email and phone** verified on the account.
3. **GitHub repository** containing this project (your fork or copy).
4. **Tools on your laptop** (for first-time cluster and ECR setup):
   - [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
   - `kubectl` ([install guide](https://kubernetes.io/docs/tasks/tools/))
   - [eksctl](https://eksctl.io/installation/) (simplest way to create EKS)
   - Docker (optional locally; CI builds in GitHub)

---

## 4. Secure the AWS account

1. Sign in to the [AWS Management Console](https://console.aws.amazon.com/).
2. Enable **MFA** on the **root** user.
3. Create an **IAM user** for day-to-day work (for example `admin-dev`) with **console password** and **access keys** only if you need CLI/automation. For learning, attaching **AdministratorAccess** is common; for production you would use least privilege.

Configure the CLI:

```bash
aws configure
```

Set default **region** (for example `us-east-1`) and use the access key for your IAM user.

---

## 5. Choose a Region

Pick one region and use it everywhere (ECR, EKS, Secrets Manager, CloudWatch, GitHub secrets). Examples: `us-east-1`, `us-west-2`, `eu-west-1`.

The Kubernetes **ConfigMap** in this repo defaults `AWS_REGION` to `us-east-1`. If you choose another region, you must change `AWS_REGION` in `deployment/k8s/configmap.yaml` before deploying (or edit after apply).

---

## 6. Create an ECR repository

1. In the console: **Elastic Container Registry** → **Repositories** → **Create repository**.
2. Name it something stable (for example `support-ops-agent`). **Private** is fine.
3. Note the **repository name**; you will use it as the GitHub secret `ECR_REPOSITORY`.

CLI equivalent:

```bash
aws ecr create-repository --repository-name support-ops-agent --region "$AWS_REGION"
```

---

## 7. Create an EKS cluster (minimal path with eksctl)

Example: one small managed node group suitable for learning (not HA; adjust for production).

```bash
export AWS_REGION=us-east-1   # your region
export CLUSTER_NAME=support-ops-demo

eksctl create cluster \
  --name "$CLUSTER_NAME" \
  --region "$AWS_REGION" \
  --nodes 2 \
  --node-type t3.small \
  --managed
```

- Wait until the cluster is **ACTIVE**.
- Note `CLUSTER_NAME` for GitHub secret `EKS_CLUSTER_NAME`.

Update kubeconfig:

```bash
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION"
kubectl get nodes
```

### 7.1 Enable IAM roles for service accounts (IRSA)

Your pods need AWS permissions for **Secrets Manager** and (if enabled) **CloudWatch Logs**. EKS uses **IRSA**.

Create the OIDC provider if it does not exist (eksctl often does this automatically; if not):

```bash
eksctl utils associate-iam-oidc-provider --cluster "$CLUSTER_NAME" --region "$AWS_REGION" --approve
```

You will create a **pod IAM role** in section 10 and attach its ARN to `deployment/k8s/serviceaccount.yaml`.

---

## 8. IAM user for GitHub Actions (push ECR + kubectl)

The workflow uses **long-lived access keys** (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`). Prefer **OIDC + short-lived roles** in real production; keys are simpler for a first setup.

Create an IAM user (for example `github-actions-support-ops`) and create **access keys**. Attach policies that allow at least:

- **ECR**: push images to your repository (or use `AmazonEC2ContainerRegistryPowerUser` scoped to your account/repo for learning).
- **EKS**: `eks:DescribeCluster` (and related read APIs used by `update-kubeconfig`).
- **Kubernetes API access**: the IAM principal must be mapped in the cluster **aws-auth** `ConfigMap`, or `kubectl` from CI will fail with unauthorized.

#### 8.1 Map the GitHub IAM user into the cluster

Get your IAM user ARN:

```bash
aws sts get-caller-identity
```

Edit the `aws-auth` ConfigMap:

```bash
kubectl edit configmap aws-auth -n kube-system
```

Under `mapUsers`, add (replace account ID and user name):

```yaml
mapUsers: |
  - userarn: arn:aws:iam::YOUR_ACCOUNT_ID:user/github-actions-support-ops
    username: github-actions-support-ops
    groups:
      - system:masters
```

Using `system:masters` is quick for learning; in production you would use a dedicated RBAC group with least privilege.

Save and exit. Test from the same machine using that user’s keys:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION"
kubectl get pods -A
```

---

## 9. OpenAI key in AWS Secrets Manager

1. Console: **Secrets Manager** → **Store a new secret** → **Other type of secret** → **Plaintext** and paste JSON:

```json
{"OPENAI_API_KEY": "sk-your-key-here"}
```

2. Name the secret `support-ops-agent/openai` (matches `AWS_SECRETS_MANAGER_SECRET_NAME` in `deployment/k8s/configmap.yaml`) or change the ConfigMap to match your secret name.

3. Note the secret **ARN** for IAM policies below.

arn:aws:secretsmanager:us-east-1:074388197187:secret:support-ops-agent/openai-vvPuwJ

---

## 10. IAM role for the Kubernetes service account (IRSA)

The **pod** must assume an IAM role to call Secrets Manager and (optionally) CloudWatch.

1. **Trust policy** (OIDC): allow `sts:AssumeRoleWithWebIdentity` for your cluster’s OIDC provider, restricted to the `support-ops-agent` namespace and `support-ops-agent` service account. AWS documents the exact JSON in [IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/create-service-account-iam-policy-and-role.html).

2. **Permissions policy** (example; tighten ARNs for production):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:SECRET_NAME_PREFIX*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "*"
    }
  ]
}
```

For least privilege on CloudWatch, scope `Resource` to your log group ARN once you know it (for example `/support-ops/agent`).

3. Create the role, note the **role ARN**.

4. In this repo, edit `deployment/k8s/serviceaccount.yaml` and set the annotation (uncomment and replace):

```yaml
eks.amazonaws.com/role-arn: arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_ROLE_NAME
```

Commit this change so CI applies the annotated ServiceAccount.

---

## 11. CloudWatch logging: two layers

### A. Container stdout (always on)

The application writes structured JSON to **stdout**. That is the standard pattern on Kubernetes. To see these logs in CloudWatch without changing code:

- Use the **CloudWatch Container Insights** / **Fluent Bit** add-on or the [AWS for Fluent Bit](https://aws.amazon.com/blogs/containers/introducing-fluent-bit-for-amazon-eks/) DaemonSet so cluster logs ship to a **CloudWatch log group** for the cluster.

Exact add-on steps depend on your EKS version; follow the current AWS documentation for “EKS logs to CloudWatch”.

### B. Direct CloudWatch handler (optional, app-level)

This repo supports **watchtower** when `ENABLE_CLOUDWATCH_LOGGING=true` (see `app/core/logging.py`). Then logs are also sent to the log group named by `CLOUDWATCH_LOG_GROUP` (default `/support-ops/agent` in `deployment/k8s/configmap.yaml`).

1. Ensure the **IRSA role** has CloudWatch Logs permissions (section 10).
2. Set in `deployment/k8s/configmap.yaml`:

```yaml
ENABLE_CLOUDWATCH_LOGGING: "true"
```

3. Commit, push, and let the pipeline redeploy—or `kubectl apply` the ConfigMap and restart the deployment.

4. In the console: **CloudWatch** → **Log groups** → open `/support-ops/agent` (or your custom name) and inspect streams.

If IAM is wrong, the app **keeps running** and logs a warning to stdout; fix the role and rollout again.

---

## 12. Align ConfigMap with your account

Before relying on CI, verify `deployment/k8s/configmap.yaml`:

| Key | Typical value |
|-----|----------------|
| `AWS_REGION` | Your region (must match cluster and ECR). |
| `AWS_SECRETS_MANAGER_SECRET_NAME` | Your Secrets Manager secret name or ARN. |
| `CLOUDWATCH_LOG_GROUP` | Desired log group path. |
| `ENABLE_CLOUDWATCH_LOGGING` | `true` or `false`. |
| `SECRETS_SOURCE` | `aws_secrets_manager` for production EKS (as in the sample). |

---

## 13. GitHub repository secrets

In GitHub: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

| Secret name | Value |
|-------------|--------|
| `AWS_ACCESS_KEY_ID` | IAM user key for CI. |
| `AWS_SECRET_ACCESS_KEY` | Matching secret key. |
| `AWS_REGION` | e.g. `us-east-1`. |
| `AWS_ACCOUNT_ID` | 12-digit account ID (`aws sts get-caller-identity --query Account --output text`). |
| `ECR_REPOSITORY` | ECR repo name (not the full URI). |
| `EKS_CLUSTER_NAME` | Your cluster name. |
| `K8S_NAMESPACE` | Must match manifests: `support-ops-agent`. |

The workflow `.github/workflows/deploy.yml` reads these names exactly.

---

## 14. Run the pipeline

1. Push the `main` (or `master`) branch to GitHub.
2. Open **Actions** and open the **ci-cd** workflow run.
3. Confirm **test** passes, then **build-push-deploy** pushes the image and runs `kubectl apply`.

If deploy fails:

- **Unauthorized from kubectl**: fix **aws-auth** mapping for the CI user (section 8.1).
- **ImagePullBackOff**: check ECR URI, region, and that the image was pushed.
- **CrashLoop / `/ready` 503**: Secrets Manager name, IRSA annotation, or secret JSON missing `OPENAI_API_KEY`.
- **No CloudWatch direct logs**: IAM on the pod role, `ENABLE_CLOUDWATCH_LOGGING`, and region.

---

## 15. Reach the API from your laptop

The Service is **ClusterIP** (`deployment/k8s/service.yaml`), so nothing is public by default.

For a quick test:

```bash
kubectl port-forward -n support-ops-agent svc/support-ops-agent 8000:80
curl -s http://localhost:8000/health
```

For HTTPS and a public URL, add an **Ingress** with **AWS Load Balancer Controller** or **API Gateway** in front; that is outside this repo’s baseline (see main `README.md`).

---

## 16. Cost hygiene after the demo

- Delete load balancers and unused **Elastic IPs**.
- Scale node groups down or delete the cluster with `eksctl delete cluster` when finished.
- **ECR** images and **CloudWatch** log storage accrue small charges; delete old images and shorten log retention if needed.

---

## 17. Quick reference: file map

| File | Purpose |
|------|---------|
| `.github/workflows/deploy.yml` | CI: test, ECR build/push, kubectl apply, rollout. |
| `deployment/k8s/namespace.yaml` | Namespace `support-ops-agent`. |
| `deployment/k8s/serviceaccount.yaml` | IRSA annotation for pod AWS role. |
| `deployment/k8s/configmap.yaml` | Non-secret env: region, Secrets Manager name, CloudWatch flags. |
| `deployment/k8s/deployment.yaml` | Image placeholder `REPLACE_IMAGE_URI` replaced in CI. |
| `deployment/k8s/service.yaml` | ClusterIP service on port 80 → container 8000. |

You now have an end-to-end path from **local Docker** to **GitHub-driven deploys on EKS** with **Secrets Manager** and **CloudWatch** aligned with this application’s configuration.
