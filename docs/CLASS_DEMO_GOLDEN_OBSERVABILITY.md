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

### User input and model output (troubleshooting)

For **`POST /agent/respond`**, logs include:

| `log_event` | What appears in `metadata` / `safe_metadata` |
|-------------|-----------------------------------------------|
| `agent_user_input` | `user_query_preview` (truncated), `request_id`, `endpoint` |
| `llm_response` | `response_preview` for **each** chat completion (enrich, plan, respond, etc.), `request_id`, `model` |
| `agent_output` | `classification`, `draft_reply_preview`, `internal_summary_preview`, `recommended_action_preview`, `policy_context_preview`, `used_tools`, `processing_time_ms` |

For **`POST /agent/stream`**, the handler logs **`agent_user_input`** before streaming; **`llm_response`** lines still include `request_id` from graph state.

Truncation is controlled by **`AGENT_IO_LOG_MAX_CHARS`** (default `4000`; set `0` to disable user/LLM text in logs). These fields may contain **learner or operator content** — restrict log access in production.

**CloudWatch Logs Insights — user + model on one request:**

If field names work in your log group:

```sql
fields @timestamp, @message, log_event, metadata.request_id as rid
| filter log_event in ["agent_user_input", "llm_response", "agent_output"]
| filter metadata.request_id = "YOUR_REQUEST_ID"
| sort @timestamp asc
```

If not, search the raw JSON line (beginner-friendly):

```sql
fields @timestamp, @message
| filter @message like /YOUR_REQUEST_ID/
| filter @message like /agent_user_input|llm_response|agent_output/
| sort @timestamp asc
```

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

### 4.3 Hands-on: CloudWatch Logs Insights (if you are new to CloudWatch)

**What this is:** **Logs Insights** is a query editor on top of log storage. You pick **which log group** to read, a **time window**, run a small **query language** (pipe syntax), and see a table of matching lines.

**Before you start**

1. You have **already sent at least one request** (§4.2) so new log events exist.
2. You know your **AWS Region** (same as the EKS cluster), e.g. `us-east-1`.
3. You know your **log group name**, e.g. `/support-ops/agent` (from `CLOUDWATCH_LOG_GROUP` in `deployment/k8s/configmap.yaml`), **or** the cluster log group if you only use Fluent Bit / Container Insights (name will differ).

**Open Logs Insights (console)**

1. Sign in to the [AWS Management Console](https://console.aws.amazon.com/).
2. **Region:** top-right menu — select the **same region** as your cluster (e.g. `N. Virginia` = `us-east-1`).
3. Search for **CloudWatch** (or open **Services** → **CloudWatch**).
4. Left sidebar → **Logs** → **Logs Insights** (under **Logs**).
5. **Select log group(s):** use the dropdown **“Log groups”** and check the group where your app’s stdout / watchtower logs go (often `/support-ops/agent` if you use direct logging).
6. **Time range:** above the query box, choose **Relative** → e.g. **15m** or **1h**, or **Custom** if you ran the curl earlier today.
7. **Run a query:** paste one of the queries below into the editor, click **Run query**.

**First query (recommended for beginners — works when each log line is JSON inside `@message`)**

EKS and Fluent Bit usually store the **whole JSON line** in the field **`@message`**. Searching that string is reliable:

```sql
fields @timestamp, @message
| filter @message like /class-demo-001/
| sort @timestamp desc
| limit 50
```

Replace `class-demo-001` with the **`request_id`** you care about (from the API response or `X-Request-ID`).

**Read the results**

- Each row is one log event. Open **`@message`**: you should see your app’s JSON (`request_id`, `log_event`, `metadata`, etc.).
- **No rows?** Widen the time range, confirm **region** and **log group**, confirm `ENABLE_CLOUDWATCH_LOGGING` / cluster logging is actually shipping logs to that group, then generate traffic again (§4.2).

**Query using JSON field names (when they resolve)**

If Insights already parses your JSON (or you use `parse` — varies by ingestion), you can filter on fields:

```sql
fields @timestamp, @message, request_id, error_code, log_event
| filter request_id = "class-demo-001"
| sort @timestamp desc
| limit 50
```

If this returns **no rows** but the `@message` **like** query above works, keep using **`filter @message like /.../`** for your class demo.

**LangChain trace lines only (when `ENABLE_LANGCHAIN_TRACE_LOGS=true`):**

```sql
fields @timestamp, @message
| filter @message like /langchain_trace/
| sort @timestamp desc
| limit 100
```

**Errors only (search in raw message):**

```sql
fields @timestamp, @message
| filter @message like /"level":"ERROR"/ or @message like /"error_code"/
| sort @timestamp desc
| limit 50
```

**Save / reuse**

- Use **Save** in the query editor to keep a named query for the next class.
- **Actions** → **Export results** if you want CSV for slides (optional).

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
