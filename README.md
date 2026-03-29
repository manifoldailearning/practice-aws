# Support Operations Agent (Agentic AI Platform Demo)

Production-style internal **Support Operations Assistant** for an AI bootcamp / learning platform. The service exposes a FastAPI API, orchestrates work with **LangGraph**, calls **OpenAI** through LangChain, loads secrets from **AWS Secrets Manager** in production, and can ship structured logs to **stdout** and optionally **Amazon CloudWatch** via `watchtower`.

This repository is intended as a **teachable but realistic** reference for how teams ship agentic services on **Amazon EKS** with **ECR**, **GitHub Actions**, and AWS observability primitives.

## Class demo (teaching)

Use these three pieces together; each file avoids duplicating the others.

| Doc | Use it for |
|-----|------------|
| **`docs/CI_CD_AWS_FROM_SCRATCH.md`** | AWS account → ECR → EKS → IRSA → Secrets Manager → CloudWatch → GitHub Actions → **`kubectl`** and **§15** demo curls. Starts with **§1.1 Class demo runbook** (step-by-step order). |
| **`docs/CLASS_DEMO_GOLDEN_OBSERVABILITY.md`** | Golden dataset, **`./scripts/run_golden_regression.sh`**, structured errors, **CloudWatch Logs Insights** queries, **`curl /metrics`** (Prometheus is metrics only — not logs). **§6** = optional **demo tool failure** / **slow policy** scenarios. |

**Suggested flow (45–60 min):**

1. **Local:** install deps, run `pytest -q` and `./scripts/run_golden_regression.sh` — same tests CI runs.
2. **Optional break:** walk through `data/golden_dataset.json` and `GET /demo/golden-dataset` (after `uvicorn` locally or in step 4).
3. **AWS:** follow **`docs/CI_CD_AWS_FROM_SCRATCH.md`** §1.1 table — deploy or use existing cluster, then **port-forward** and run **§15** curls.
4. **Observability:** open **CloudWatch Logs** and run **Logs Insights** queries from **`docs/CLASS_DEMO_GOLDEN_OBSERVABILITY.md`** — use `X-Request-ID` from your curl.

**Quick local commands (no cluster):**

```bash
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest -q
./scripts/run_golden_regression.sh
```

**Quick API after deploy** (see CI/CD doc §15 for full list): `kubectl port-forward -n support-ops-agent svc/support-ops-agent 8000:80` then `curl http://localhost:8000/health`.

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
scripts/                  # e.g. run_golden_regression.sh (class / CI)
data/golden_dataset.json  # curated labels for regression demos
docs/                     # CI_CD_AWS_FROM_SCRATCH.md, CLASS_DEMO_GOLDEN_OBSERVABILITY.md
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

**Golden regression (class / CI):** deterministic tests assert each row in `data/golden_dataset.json` matches `POST /agent/respond` when the graph is a stub (see `tests/golden/test_golden_regression.py`). Run `./scripts/run_golden_regression.sh` or `pytest tests/golden/test_golden_regression.py -v`. Details: `docs/CLASS_DEMO_GOLDEN_OBSERVABILITY.md` §2.1. This is called out in **`docs/CI_CD_AWS_FROM_SCRATCH.md`** §1.1 step 2.

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
| `ENABLE_LANGCHAIN_TRACE_LOGS` | LangChain span-style JSON logs (more volume; good for CloudWatch Logs Insights demos) |
| `AGENT_IO_LOG_MAX_CHARS` | Max length for logged user query / LLM / draft text per field (`0` disables; default `4000`) |
| `ENABLE_DEMO_SCENARIOS` | If `true`, `user_query` may include `[demo:tool-failure]` or `[demo:slow-tool]` for policy-node demos (see `docs/CLASS_DEMO_GOLDEN_OBSERVABILITY.md` §6) |
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

1. Install dependencies and run **`pytest`** (includes unit, integration, and golden tests).
2. `docker build` and push to ECR with tag `${{ github.sha }}`.
3. `aws eks update-kubeconfig` and `kubectl apply` manifests.
4. `kubectl rollout status` for the deployment.

**Class tip:** show the **Actions** tab for the same commit students ran locally; the **test** job must pass before the image is built. Full AWS setup: `docs/CI_CD_AWS_FROM_SCRATCH.md` §1.1 and §14.

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
| GET | `/metrics` | Prometheus text metrics (scraped by Prometheus; not application logs) |
| GET | `/demo/golden-dataset` | Teaching golden examples (JSON) |
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
| `/demo/golden-dataset` 500 / `FileNotFoundError` for `golden_dataset.json` | Rebuild and redeploy the image so `data/` is included (see `Dockerfile`); older images only copied `app/`. |

## Production notes and tradeoffs

- **Structured JSON logs** include `request_id`, `route`, `environment`, optional `node_name`, `duration_ms`, and safe metadata — never secrets. For troubleshooting, **`log_event`** values such as `agent_user_input`, `llm_response`, and `agent_output` include **truncated** user text and model output (see `AGENT_IO_LOG_MAX_CHARS`); treat logs as potentially sensitive.
- **Metrics:** `GET /metrics` exposes Prometheus counters/histograms; `GET /metrics-summary` returns JSON. **Logs** go to **CloudWatch** (or stdout) — not to Prometheus. See `docs/CLASS_DEMO_GOLDEN_OBSERVABILITY.md` for a class walkthrough (golden dataset, errors, CloudWatch Insights, Prometheus).
- **Graph** uses async nodes and `tenacity` around LLM calls for transient API failures.
- **State** is TypedDict-based; extend with reducers if you add conversational memory.
- **Ingress / TLS** omitted intentionally — add per your platform.

## License

Internal / educational use for the Agentic AI Bootcamp demo.
