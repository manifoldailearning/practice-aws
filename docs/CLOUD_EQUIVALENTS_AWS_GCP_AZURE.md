# AWS, GCP, and Azure: equivalent components (same deployment approach)

This guide maps the **deployment pattern used in this repository**—**Docker** → **private registry** → **managed Kubernetes** → **centralized secrets** → **logs**, with **GitHub Actions** driving CI/CD—to the closest equivalents on **Google Cloud Platform (GCP)** and **Microsoft Azure**.

It is meant for **mental models and teaching**, not as copy-paste runbooks. Service names, SKUs, and pricing change; always check each vendor’s current documentation.

**Companion:** step-by-step AWS setup for this repo: [`CI_CD_AWS_FROM_SCRATCH.md`](CI_CD_AWS_FROM_SCRATCH.md).

---

## 1. The pattern (vendor-neutral)

Regardless of cloud, the architecture is the same idea:

```text
Git push → CI runs tests (regression gate) → build image → push to registry
       → apply Kubernetes manifests → pods run on managed Kubernetes
       → app reads secrets from a managed secret store
       → logs: stdout (cluster agent) and/or direct SDK to a log backend
```

**GitHub Actions** is **cloud-agnostic**: the YAML changes mainly in **how the workflow authenticates** (OIDC or keys) and **which CLI** you call (`aws`, `gcloud`, `az`).

---

## 2. Core mapping table

| Concern | AWS (this repo) | Google Cloud (GCP) | Microsoft Azure |
|--------|-------------------|--------------------|-----------------|
| **Private container registry** | **Amazon ECR** | **Artifact Registry** (recommended; *Container Registry* is legacy) | **Azure Container Registry (ACR)** |
| **Managed Kubernetes** | **Amazon EKS** | **Google Kubernetes Engine (GKE)** | **Azure Kubernetes Service (AKS)** |
| **Central secret store (API key, JSON)** | **AWS Secrets Manager** (or **SSM Parameter Store** for simpler cases) | **Secret Manager** | **Azure Key Vault** (secrets) |
| **Pod → cloud identity (no long-lived keys in the pod)** | **IAM Roles for Service Accounts (IRSA)** | **Workload Identity** (Kubernetes SA ↔ GCP service account) | **Workload Identity** / **Azure AD workload identity** (OIDC federation; often paired with **managed identities** on nodes) |
| **Structured / centralized logs** | **Amazon CloudWatch Logs** (+ optional in-app **watchtower** to CloudWatch) | **Google Cloud Logging** (part of **Operations**; formerly “Stackdriver”) | **Azure Monitor Logs** (**Log Analytics workspace**) |
| **Metrics & dashboards (typical pairing)** | **CloudWatch Metrics** | **Cloud Monitoring** | **Azure Monitor** metrics |
| **CLI for automation** | **AWS CLI** | **gcloud** (+ **kubectl** with GKE credentials) | **Azure CLI (`az`)** (+ **kubectl** for AKS) |

---

## 3. Component-by-component notes

### 3.1 Container registry

| | AWS | GCP | Azure |
|---|-----|-----|-------|
| **Role** | Store versioned images; CI pushes; cluster pulls. | Same. | Same. |
| **Rough analogy** | Docker Hub, but private and in your account. | Same. | Same. |

- **ECR** ↔ **Artifact Registry** ↔ **ACR**: all support image scanning, retention policies, and regional replication in various forms (exact features differ).

### 3.2 Managed Kubernetes

| | AWS | GCP | Azure |
|---|-----|-----|-------|
| **Role** | Control plane managed by the cloud; you run worker nodes (or Fargate profiles on EKS). | GKE: Autopilot (less node ops) or Standard node pools. | AKS: control plane managed; you choose node pools / VM SKUs. |

- **EKS** ↔ **GKE** ↔ **AKS**: all speak **standard Kubernetes** (`kubectl`, Deployments, Services, ConfigMaps). Your `deployment/k8s/*.yaml` ideas transfer; you still must adapt **cloud-specific** pieces: **ingress**, **load balancers**, **identity**, and **CSI drivers** for secrets if you mount them as volumes.

### 3.3 Secrets for the application

This repo’s app loads **`OPENAI_API_KEY`** from the environment (local) or from **Secrets Manager** (AWS) via IAM.

| | AWS | GCP | Azure |
|---|-----|-----|-------|
| **Managed store** | Secrets Manager | Secret Manager | Key Vault |
| **Typical pod access** | IRSA + SDK (`boto3`) or CSI driver | Workload Identity + **Google client libraries** or CSI | Managed identity / workload identity + **Azure SDK** or **Secrets Store CSI** |

Conceptually: **one JSON secret in a vault** + **least-privilege IAM** on the workload is the same pattern on all three clouds.

### 3.4 Logging

| Layer | AWS | GCP | Azure |
|-------|-----|-----|-------|
| **Container stdout/stderr** | Collected by DaemonSet / add-on → **CloudWatch Logs** | **Fluent Bit** / GKE logging → **Cloud Logging** | **Container Insights** / Azure Monitor agent → **Log Analytics** |
| **App pushes logs via SDK** (e.g. this repo’s optional **watchtower**) | CloudWatch Logs API | Cloud Logging API | Monitor ingestion APIs (often stdout is preferred) |

**Teaching point:** On Kubernetes, **logging to stdout in JSON** is portable; the **cluster integration** is what changes (CloudWatch vs Cloud Logging vs Log Analytics).

### 3.5 Identity: “the pod is allowed to call the API”

| | AWS | GCP | Azure |
|---|-----|-----|-------|
| **Name** | IRSA | Workload Identity | Workload identity (Entra ID / federated credentials) |
| **Idea** | Map K8s `ServiceAccount` → IAM role | Map K8s SA → GCP service account | Map K8s SA → Azure identity |
| **Avoids** | Static cloud keys inside the container image | Same | Same |

---

## 4. CI/CD (GitHub Actions) and the regression gate

The **regression gate** (tests must pass before deploy) is **identical in concept** on every cloud: your workflow runs **`pytest`** (or similar) first; only on success do you **build/push** and **deploy**.

| Piece | Same everywhere? | What changes per cloud |
|-------|-------------------|-------------------------|
| **Test job** | Yes | Install deps, env vars for CI |
| **Build Docker image** | Yes | None for a standard `Dockerfile` |
| **Push to registry** | Concept same | Login: `aws ecr get-login-password` vs `gcloud auth configure-docker` vs `az acr login` |
| **Deploy to cluster** | Concept same | `aws eks update-kubeconfig` vs `gcloud container clusters get-credentials` vs `az aks get-credentials` |
| **Auth from GitHub to cloud** | Pattern same | **OIDC federation** (recommended) or repository secrets for cloud credentials |

So: **GCP and Azure do not replace “the regression gate”**—they replace **where the image goes** and **which cluster API** you call after tests pass.

---

## 5. Minimal “if you ported this repo” checklist

| Step | AWS | GCP | Azure |
|------|-----|-----|-------|
| 1 | Create ECR repo | Create Artifact Registry repo | Create ACR |
| 2 | Create EKS cluster | Create GKE cluster | Create AKS cluster |
| 3 | Configure IRSA for Secrets + logs | Enable Workload Identity + IAM on GCP SA | Configure workload identity + Key Vault access |
| 4 | Store OpenAI key in Secrets Manager | Store in Secret Manager | Store in Key Vault |
| 5 | Point app config at region + secret name | Use GCP-specific env or SDK defaults | Use Azure Key Vault URI / secret names |
| 6 | GitHub Actions: authenticate, push, `kubectl apply` | Same flow with `gcloud` | Same flow with `az` |

Application code that uses **`boto3`** and **watchtower** is **AWS-specific**; a port would swap in **GCP** or **Azure** SDKs (or rely on **stdout-only** logging for maximum portability).

---

## 6. When names sound similar

- **“Workload Identity”** on **GCP** and **Azure** both mean *Kubernetes workloads get cloud identities*—they are **related ideas** to **IRSA**, but **not** interchangeable configuration.
- **CloudWatch** vs **Cloud Logging** vs **Azure Monitor**: all are **telemetry backends**; naming is confusing because every vendor uses “cloud” in product names.

---

## 7. Further reading (official entry points)

- **GCP:** [Artifact Registry](https://cloud.google.com/artifact-registry/docs), [GKE](https://cloud.google.com/kubernetes-engine/docs), [Workload Identity](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity), [Secret Manager](https://cloud.google.com/secret-manager/docs), [Cloud Logging](https://cloud.google.com/logging/docs).
- **Azure:** [Azure Container Registry](https://learn.microsoft.com/azure/container-registry/), [AKS](https://learn.microsoft.com/azure/aks/), [Azure Key Vault](https://learn.microsoft.com/azure/key-vault/), [Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/), [Workload identity in AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview).

---

*This file is a conceptual map for the same deployment approach as this repository; it is not a substitute for each platform’s security and pricing guidance.*
