# Support Operations Agent (Agentic AI Platform Demo)

Production-style internal **Support Operations Assistant** for an AI bootcamp / learning platform. The service exposes a FastAPI API, orchestrates work with **LangGraph**, calls **OpenAI** through LangChain, loads secrets from **AWS Secrets Manager** in production, and can ship structured logs to **stdout** and optionally **Amazon CloudWatch** via `watchtower`.

This repository is intended as a **teachable but realistic** reference for how teams ship agentic services on **Amazon EKS** with **ECR**, **GitHub Actions**, and AWS observability primitives.

## Use case

Program operations and support teams ask questions such as:

- What is covered in Week 6?
- A learner wants to defer to the next cohort — draft a reply.
- Classify whether a message is access, payment, deferment, or technical.
- Summarize a learner message for internal escalation.
- Suggest the next best support action.

The agent returns structured JSON (classification, policy context, recommended action, draft reply, internal summary, tool usage, latency).

## High-level architecture

```text
Client Request
   -> FastAPI
   -> LangGraph Agent
   -> Tools / Policy Store
   -> OpenAI
   -> Structured Logs
   -> stdout / CloudWatch
```

### LangGraph nodes

1. **classify** — `classify_issue_tool`
2. **enrich** — LLM summarizes intent
3. **policy_lookup** — `search_bootcamp_policy_tool`
4. **planning** — LLM plans recommended action (node name `planning` avoids LangGraph state key collision)
5. **respond** — `draft_response_tool` + LLM polish + internal summary
6. **format_output** — light guardrail / truncation

## Repository layout

```text
app/
  main.py                 # FastAPI app, lifespan, middleware, exception handlers
  api/                    # routes, schemas, request correlation middleware
  core/                   # config, secrets, logging, metrics, LLM, readiness
  agents/                 # LangGraph graph + typed state + nodes
  tools/                  # LangChain tools (policy, classification, drafting)
  services/               # policy store, request context (contextvars)
deployment/k8s/           # namespace, service account, configmap, deployment, service
.github/workflows/        # CI: test, build/push ECR, kubectl apply, rollout
tests/                    # unit + integration (mocked agent)
```

## Local development

**Prerequisites:** Python 3.11, an OpenAI API key.

1. Create a virtual environment and install dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.

3. Run the API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

4. Example request:

```bash
curl -s http://localhost:8000/agent/respond \
  -H 'Content-Type: application/json' \
  -d '{"user_query":"A learner wants to defer to the next cohort because of timing. Draft a reply and classify."}'
```

### Configuration (`pydantic-settings`)

Key settings (see `app/core/config.py`):

| Setting | Purpose |
|--------|---------|
| `APP_NAME` | Service name |
| `ENVIRONMENT` | e.g. `development`, `staging`, `production` |
| `LOG_LEVEL` | Logging level |
| `OPENAI_MODEL` | Default model (e.g. `gpt-4.1-nano`) |
| `AWS_REGION` | Region for boto3 clients |
| `AWS_SECRETS_MANAGER_SECRET_NAME` | Secret name/ARN for production JSON |
| `CLOUDWATCH_LOG_GROUP` / `CLOUDWATCH_LOG_STREAM_PREFIX` | Direct CloudWatch logging |
| `ENABLE_CLOUDWATCH_LOGGING` | Toggle watchtower handler |
| `REDIS_URL` | Optional future cache |
| `REQUEST_TIMEOUT_SECONDS` | Agent / upstream timeout |
| `SECRETS_SOURCE` | `env`, `aws_secrets_manager`, or `auto` |

**Secrets:** `OPENAI_API_KEY` is read from the environment for local (`SECRETS_SOURCE=env`). In production, JSON stored in Secrets Manager must include `"OPENAI_API_KEY": "..."`. The app never logs secret values.

## Docker

Build and run locally:

```bash
docker build -t support-ops-agent:local .
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e SECRETS_SOURCE=env \
  support-ops-agent:local
```

The image runs as non-root (`UID 10001`), uses a slim Python 3.11 base, copies `requirements.txt` before application code for layer caching, and starts with `uvicorn` exec form.

## AWS Secrets Manager

1. Create a secret (e.g. `support-ops-agent/openai`) with **SecretString** JSON:

```json
{"OPENAI_API_KEY": "sk-..."}
```

2. Grant the workload identity (IRSA role attached to the Kubernetes `ServiceAccount`) permission:

- `secretsmanager:GetSecretValue` on that secret ARN (and `kms:Decrypt` if using CMK).

3. Set `SECRETS_SOURCE=aws_secrets_manager` (or `ENVIRONMENT=production` with `SECRETS_SOURCE=auto`).

**Why not Kubernetes Secrets for the OpenAI key?** Central rotation, audit, and a single source of truth are easier in Secrets Manager; the pod never stores the key in etcd as a static Secret manifest.

## CloudWatch logging

- **Always** log JSON to **stdout/stderr** in containers so EKS / CloudWatch log drivers can collect them.
- Optionally set `ENABLE_CLOUDWATCH_LOGGING=true` to attach a **watchtower** `CloudWatchLogHandler` for a **direct** push to a log group (useful when you want structured logs without relying on the cluster log pipeline).

**IAM (direct handler):** allow `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` on the configured log group / stream prefix.

If CloudWatch setup fails, the app logs a warning and **continues** with stdout only.

### When to use which

| Approach | When it helps |
|---------|----------------|
| stdout only | Default; works everywhere; EKS DaemonSet / Fluent Bit / CW agent picks it up |
| Direct watchtower | Quick path to a dedicated log group without changing cluster logging config |

## Amazon ECR

Authenticate and push (example):

```bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker tag support-ops-agent:local "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${GIT_SHA}"
docker push "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${GIT_SHA}"
```

Use **immutable tags** (git SHA), not only `latest`.

## GitHub Actions

Workflow: `.github/workflows/deploy.yml`

1. Install dependencies and run `pytest`.
2. `docker build` and push to ECR with tag `${{ github.sha }}`.
3. `aws eks update-kubeconfig` and `kubectl apply` manifests.
4. `kubectl rollout status` for the deployment.

**Repository secrets (examples):**

- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (prefer OIDC/IRSA for production)
- `AWS_REGION`, `AWS_ACCOUNT_ID`, `ECR_REPOSITORY`, `EKS_CLUSTER_NAME`, `K8S_NAMESPACE`

**Namespace:** manifests use `support-ops-agent`. Set `K8S_NAMESPACE` to that value for rollout unless you change YAML consistently.

## EKS deployment assumptions

- Cluster already exists and `kubectl` context is configured (CI uses `aws eks update-kubeconfig`).
- **IRSA** (recommended): annotate `deployment/k8s/serviceaccount.yaml` with `eks.amazonaws.com/role-arn` for Secrets Manager + (optional) CloudWatch.
- Namespace and workloads are applied from `deployment/k8s/`.
- No Helm / Terraform / ingress controller in this baseline (add an `Ingress` or API Gateway separately if needed).

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (config + secrets loadable; no secret values) |
| GET | `/metrics-summary` | In-memory counters / latency / agent invocations |
| GET | `/config/check` | Safe config metadata only |
| POST | `/agent/respond` | Full graph run, JSON body |
| POST | `/agent/stream` | SSE stream of LangGraph `updates` chunks |

## Troubleshooting

| Symptom | Likely cause |
|--------|----------------|
| Startup fails on missing key | `OPENAI_API_KEY` not in env (local) or Secrets Manager JSON (AWS) |
| `/ready` 503 | Same as above, or IAM / network to Secrets Manager |
| OpenAI timeouts | Increase `REQUEST_TIMEOUT_SECONDS`; check model availability |
| No CloudWatch direct logs | `ENABLE_CLOUDWATCH_LOGGING` false, IAM, or watchtower init failed (check stdout warning) |
| kubectl apply errors | Namespace ordering; CRB/RBAC; image pull from ECR |

## Production notes and tradeoffs

- **Structured JSON logs** include `request_id`, `route`, `environment`, optional `node_name`, `duration_ms`, and safe metadata — never secrets.
- **Metrics** are in-process (demo); swap for Prometheus / ADOT in production.
- **Graph** uses async nodes and `tenacity` around LLM calls for transient API failures.
- **State** is TypedDict-based; extend with reducers if you add conversational memory.
- **Ingress / TLS** omitted intentionally — add per your platform.

## License

Internal / educational use for the Agentic AI Bootcamp demo.
