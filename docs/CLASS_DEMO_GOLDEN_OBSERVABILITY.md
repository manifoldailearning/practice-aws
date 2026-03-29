# Class demo: golden dataset, errors, CloudWatch, and Prometheus

**Start here for the big picture:** `README.md` → **Class demo (teaching)**. For **AWS / EKS / CI** steps and **port-forward + curl** scripts, use **`docs/CI_CD_AWS_FROM_SCRATCH.md`** §1.1 and §15.

This guide supports a live walkthrough of **regression-style examples**, **structured errors**, **logs and traces in Amazon CloudWatch Logs**, and **metrics in Prometheus**. Read the short conceptual note below first so students are not confused about **logs vs metrics**.

---

## 1. Logs (CloudWatch) vs metrics (Prometheus)

| What | Where it goes | How you view it |
|------|----------------|-----------------|
| **Application logs** (JSON lines, stack traces, LangChain span logs) | **stdout** in the pod → cluster log pipeline → often **CloudWatch Logs**; optionally **direct** to a log group via `watchtower` when `ENABLE_CLOUDWATCH_LOGGING=true` | **CloudWatch** → **Log groups** → **Logs Insights** |
| **Numeric metrics** (request counts, latency histograms) | **Prometheus** scrapes an HTTP **`/metrics`** endpoint (text format); or you can ship similar signals to **CloudWatch Metrics** with an agent | **Prometheus UI**, **Amazon Managed Grafana**, or **Grafana** scraping the cluster |

**Prometheus does not store full application log lines.** If someone asks “can we see application logs in Prometheus?”, the accurate answer is: **no** — Prometheus holds **time-series metrics**. **Logs** belong in **CloudWatch Logs** (or another log backend). This app exposes **`GET /metrics`** so a classroom Prometheus stack can **scrape counters and histograms**, while **JSON logs** (including trace-style span events) show up in **CloudWatch** when logging is wired as in `docs/CI_CD_AWS_FROM_SCRATCH.md`.

---

## 2. Golden dataset (teaching)

**Purpose:** A small, versioned set of **fixed user queries** with **expected classification labels** so you can discuss regression testing, data quality, and “known good” behavior without running a full offline eval platform.

**File:** `data/golden_dataset.json`

**API (read-only, no LLM call):**

```bash
curl -s http://localhost:8000/demo/golden-dataset | jq .
```

**Automated checks:** `tests/golden/test_golden_dataset.py` validates that the file loads and that case IDs are unique.

### 2.1 Regression testing (class demo)

The suite **`tests/golden/test_golden_regression.py`** runs **`POST /agent/respond`** once per golden row and asserts `classification` equals `expected_classification`.

For teaching, the test replaces the LangGraph with a **deterministic stub** that returns the expected label for each known `user_query`. That keeps CI fast and non-flaky while you explain the real-world pattern: *golden file → automated checks → fail the build when behavior drifts.*

**Run in the terminal (good to project):**

```bash
cd /path/to/practice-aws
source .venv/bin/activate   # if you use a venv
pytest tests/golden/test_golden_regression.py -v --tb=short
```

Or use the helper script (same command):

```bash
./scripts/run_golden_regression.sh
```

You should see one **passed** line per case id (for example `deferment-001`, `access-001`, …).

**What to say in class**

1. **Stub vs real LLM:** With a real model, labels can change run-to-run; teams often use **offline eval**, **snapshot tests with tolerances**, or **human review** for production gates. This repo uses a stub so **regression mechanics** are clear without API cost.
2. **Adding a case:** Edit `data/golden_dataset.json`, then re-run pytest; the new row is picked up automatically.
3. **Optional extension:** Run the same golden queries against **staging** with the real graph and compare to labels manually or with a separate flaky/slow job (not in this repo by default).

**Class script ideas:**

1. Open `data/golden_dataset.json` and explain `id`, `user_query`, `expected_classification`, `tags`.
2. Call `GET /demo/golden-dataset` and show the same payload through the API.
3. Run **`pytest tests/golden/test_golden_regression.py -v`** and walk through the passing tests.
4. (Optional) Change one `expected_classification` in the JSON to a wrong value, re-run pytest, and show a **failure** — that is regression testing catching a “drift” from the agreed golden labels.

---

## 3. Error handling and structured logs (CloudWatch)

The app logs **JSON** with fields such as `request_id`, `route`, `environment`, and (on errors) `error_code`, `error_type`, `log_event`, plus optional `metadata` / `safe_metadata`.

**Examples of `error_code` values:**

| Situation | `error_code` / `log_event` | HTTP |
|-----------|------------------------------|------|
| Agent exceeded `REQUEST_TIMEOUT_SECONDS` | `AGENT_TIMEOUT` / `agent_timeout` | 504 |
| Graph or tool raised | `AGENT_INVOCATION_FAILED` (with `logger.exception` traceback) | 500 |
| Pydantic validation failed | `VALIDATION_ERROR` / `validation_error` | 422 |
| Unhandled exception | `INTERNAL_ERROR` / `unhandled_exception` | 500 |
| Other `AppException` | `exc.code` uppercased / `app_exception` | varies |

**LangGraph / LangChain span traces as logs:** Set `ENABLE_LANGCHAIN_TRACE_LOGS=true`. The callback in `app/core/trace_logging_callback.py` emits **span-style JSON** (`langchain_trace …`, `trace_event`, `run_id`, etc.) on the **same logging pipeline** as the rest of the app (stdout → aggregator → CloudWatch, and watchtower if enabled). This is **not** a substitute for the LangSmith UI; it is **correlated logs** for CloudWatch Logs Insights.

---

## 4. Detailed steps: show logs and traces in CloudWatch (EKS)

Assume the service is already deployed per `docs/CI_CD_AWS_FROM_SCRATCH.md`.

### 4.1 Turn on direct CloudWatch logging (optional but clear for demos)

1. Confirm the pod **IRSA role** allows CloudWatch Logs (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`, …) on your log group (see CI/CD doc §10).
2. In `deployment/k8s/configmap.yaml`, set:
   - `ENABLE_CLOUDWATCH_LOGGING: "true"`
   - `CLOUDWATCH_LOG_GROUP: "/support-ops/agent"` (or your chosen name)
3. **Optional (more verbose, good for “tracing in CloudWatch”):** set `ENABLE_LANGCHAIN_TRACE_LOGS: "true"`.
4. Apply the ConfigMap and restart the deployment:
   ```bash
   kubectl apply -f deployment/k8s/configmap.yaml
   kubectl rollout restart deployment/support-ops-agent -n support-ops-agent
   ```
5. In **AWS Console** → **CloudWatch** → **Log groups** → open `/support-ops/agent` (or your name) and inspect **log streams**.

### 4.2 Generate traffic

```bash
kubectl port-forward -n support-ops-agent svc/support-ops-agent 8000:80

curl -s http://localhost:8000/agent/respond \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: class-demo-001' \
  -d '{"user_query":"A learner wants to defer to the next cohort."}'
```

Copy `request_id` from the JSON response (or use `X-Request-ID`).

### 4.3 CloudWatch Logs Insights queries

**Filter by request:**

```sql
fields @timestamp, message, request_id, error_code, log_event
| filter request_id = "class-demo-001"
| sort @timestamp desc
| limit 50
```

**LangChain trace lines only (when `ENABLE_LANGCHAIN_TRACE_LOGS=true`):**

```sql
fields @timestamp, message, metadata.trace_event as trace_event, metadata.run_id as run_id
| filter message like /langchain_trace/
| sort @timestamp desc
| limit 100
```

**Errors only:**

```sql
fields @timestamp, message, error_code, level, exception
| filter level = "ERROR" or ispresent(error_code)
| sort @timestamp desc
| limit 50
```

---

## 5. Detailed steps: Prometheus metrics (not logs)

### 5.1 What this app exposes

- **`GET /metrics`** — Prometheus text exposition (from `prometheus_client`).
- Useful series include `support_ops_http_requests_total`, `support_ops_http_request_duration_seconds`, `support_ops_agent_invocations_total`.

### 5.2 Classroom options

**Option A — Port-forward and curl (fastest):**

```bash
kubectl port-forward -n support-ops-agent svc/support-ops-agent 8000:80
curl -s http://localhost:8000/metrics | head -40
```

**Option B — Prometheus in the cluster:** Deploy Prometheus (or use **Amazon Managed Service for Prometheus**) and add a **ServiceMonitor** scrape config pointing at the pod’s `/metrics` port. You will see **counters and histograms**, not log lines.

**Option C — Compare with JSON metrics:** `GET /metrics-summary` remains a human-friendly JSON snapshot of the in-process registry (same conceptual idea as the Prometheus counters, but different format).

---

## 6. Suggested 20-minute class flow

1. **Golden dataset + regression** (7 min): Show `data/golden_dataset.json` → `GET /demo/golden-dataset` → run `pytest tests/golden/test_golden_regression.py -v` (optionally break one label and re-run to show failure).
2. **Errors** (3 min): Trigger a validation error (`POST /agent/respond` with `{}`) and show `422` + structured log fields.
3. **CloudWatch** (6 min): Enable logging flags, tail log group, run Insights query by `request_id`, optionally enable LangChain trace logs and run the trace query.
4. **Prometheus** (4 min): `curl /metrics`, explain that **logs** are not here; Prometheus is for **red** and **SLO-style** dashboards.

---

## 7. File map

| File | Role |
|------|------|
| `data/golden_dataset.json` | Golden examples |
| `app/core/golden_dataset.py` | Loader |
| `app/api/demo_routes.py` | `GET /demo/golden-dataset` |
| `app/core/logging.py` | JSON formatter + optional CloudWatch |
| `app/core/trace_logging_callback.py` | Span-style logs for LangChain |
| `app/core/langsmith_tracing.py` | RunnableConfig metadata + callbacks |
| `app/core/prometheus_metrics.py` | Prometheus metric definitions |
| `app/main.py` | `/metrics`, middleware, exception logging |
| `app/api/routes.py` | Agent error codes on timeout / failure |
| `tests/golden/test_golden_regression.py` | Parametrized regression vs golden labels (stub graph) |
| `scripts/run_golden_regression.sh` | One-liner to run the regression suite |
