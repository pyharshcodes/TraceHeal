# TraceHeal: System Architecture Overview

TraceHeal is an autonomous incident investigation and shadow-verified remediation platform for distributed cloud-native microservices.

## 1. Core Paradigm: Closed-Loop Empirical Verification

TraceHeal enforces a scientific, evidence-first incident lifecycle:
$$\text{Trace} \longrightarrow \text{Hypothesize} \longrightarrow \text{Reproduce in Sandbox} \longrightarrow \text{Verify} \longrightarrow \text{Remediate} \longrightarrow \text{Validate}$$

Unlike conversational AIOps tools that treat unverified LLM text output as ground truth, TraceHeal treats every AI diagnosis as an unconfirmed hypothesis until it is empirically reproduced and validated inside an isolated execution environment.

---

## 2. Part 1: Core Foundation & Data Architecture

Part 1 establishes the persistent state store and data models using an asynchronous SQLite engine configured with high-performance Write-Ahead Logging (WAL) and strict foreign key integrity.

### Data Entities & Relational Schema:

```
┌────────────────────────────────────────────────────────────────────────┐
│                               INCIDENT                                 │
│  • id (UUID)                 • title (String)                          │
│  • status (Enum)             • severity (Enum)                         │
│  • suspect_service (String)  • root_cause_summary (Text)               │
│  • blast_radius_json (JSON)  • created_at / updated_at                 │
└───────┬──────────────────┬─────────────────┬─────────────────┬─────────┘
        │ 1                │ 1               │ 1               │ 1
        ▼ *                ▼ *               ▼ *               ▼ *
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│TELEMETRY_SPAN│   │  HYPOTHESIS  │   │ REMEDIATION  │   │ AUDIT_EVENT  │
│• trace_id    │   │• rank        │   │• patch_type  │   │• event_type  │
│• span_id     │   │• proposed_   │   │• diff_content│   │• actor       │
│• parent_id   │   │  cause       │   │• policy_check│   │• details_json│
│• duration_ms │   │• status      │   │• approval_   │   │• created_at  │
│• status_code │   └──────┬───────┘   │  status      │   └──────────────┘
└──────────────┘          │ 1         └──────────────┘
                          ▼ *
                   ┌──────────────┐
                   │ SANDBOX_RUN  │
                   │• port        │
                   │• exit_code   │
                   │• reproduction│
                   │  _verified   │
                   └──────────────┘
```

### Incident Lifecycle State Machine:
1. `DETECTED`: Metric anomaly threshold or error rate breach captured.
2. `INVESTIGATING`: OpenTelemetry spans and call trees analyzed by agents.
3. `REPRODUCING`: Suspect service spun up in isolated sandbox with synthetic payload.
4. `VERIFIED`: Sandbox reproduces failure signature (empirical proof).
5. `REMEDIATED`: Policy-checked configuration or code patch applied in sandbox.
6. `RESOLVED`: Live service validated with healthy baseline metrics.
7. `CLOSED`: Post-incident review dossier and Pull Request archived.

---

## 3. Configuration & Environment Variables

All settings are managed via Pydantic Settings (`backend.app.core.config.Settings`) reading from `.env` or system environment variables prefixed with `TRACEHEAL_`.

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `TRACEHEAL_ENV` | `development` | Environment mode (`development`, `production`). |
| `TRACEHEAL_PORT` | `8000` | Port for TraceHeal Core API & SSE stream. |
| `TRACEHEAL_DATABASE_URL` | `sqlite+aiosqlite:///./traceheal.db` | Async database connection string. |
| `TRACEHEAL_LOG_LEVEL` | `INFO` | Console logging verbosity. |
| `TRACEHEAL_SANDBOX_BASE_PORT` | `9100` | Base port offset for ephemeral sandbox runtimes. |
| `TRACEHEAL_LLM_PROVIDER` | `mock` | Reasoning provider (`mock`, `openai`, `anthropic`). |

---

## 4. Part 2: Target Microservice Architecture & Chaos Engine

Part 2 introduces a realistic, multi-tier interconnected microservice ecosystem designed to demonstrate real distributed tracing, cascaded failures, and empirical sandbox reproduction:

```
                  ┌──────────────────────┐
                  │    Traffic / User    │
                  └──────────┬───────────┘
                             │ POST /api/v1/orders/checkout
                             ▼
                  ┌──────────────────────┐
                  │    API Gateway       │  Port 8080
                  └──────────┬───────────┘
                             │ POST /orders/process
                             ▼
                  ┌──────────────────────┐
                  │    Order Service     │  Port 8081
                  └──┬─────────────────┬─┘
  POST /inventory/   │                 │ POST /payments/charge
  reserve            ▼                 ▼
         ┌───────────────┐        ┌──────────────────────┐
         │Inventory Svc  │        │   Payment Service    │  Port 8082
         │(Port 8083)    │        │  [DB Connection Pool]│
         └───────────────┘        └──────────────────────┘
```

### Key Components:
1. **W3C Distributed Trace Context (`target_services/tracer.py`)**:
   - Conforms to standard `00-{trace_id}-{span_id}-01` header specification.
   - Pure ASGI `TraceContextMiddleware` extracts parent headers, assigns child spans, and binds coroutine context variables without stream buffering overhead.
   - Captured spans are buffered in an in-memory `SpanCollector` with query and filtering APIs.
2. **Traced Client (`target_services/client.py`)**:
   - Manages persistent connection pooling via HTTPX.
   - Automatically injects `traceparent` headers into outbound requests, recording client spans with durations and error attributes.
3. **Payment Service & Simulated Database Pool (`target_services/payment_service.py`)**:
   - Models realistic connection pool saturation (`DBPoolExhaustionError`).
   - Supports live reconfiguration of pool capacity and acquisition timeouts.
4. **Chaos Injection Engine (`target_services/chaos.py`)**:
   - Controls scenarios: `DB_POOL_EXHAUSTION`, `LATENCY_SPIKE`, `DEADLOCK`, and `INVENTORY_OUTAGE`.
   - Supports single-command cluster-wide reset to healthy baseline state.
5. **Cluster Orchestrator & Traffic Generator (`target_services/cluster.py`, `target_services/traffic.py`)**:
   - Programmatically spins up and shuts down all 4 microservices in asyncio tasks.
   - Synthesizes baseline checkout transactions and burst traffic bursts.

---

## 5. Part 3: Telemetry Ingestion Pipeline & Graph Analysis Engine

Part 3 implements the ingestion gateway, hierarchical DAG reconstruction, causal failure origin analysis, and dynamic service dependency inference:

```
[Target Services / OTel Spans]
             │
             │ HTTP POST /api/v1/telemetry/spans
             ▼
┌────────────────────────────────────────────────────────┐
│              TraceHeal Ingestion Gateway               │
│               (backend/app/main.py)                    │
└────────────────────────────┬───────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│             SQLite WAL Relational Storage              │
│                 (telemetry_spans table)                │
└────────┬───────────────────┬───────────────────┬───────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Trace DAG Trees │ │ Failure Origin  │ │ Service Topology│
│ (trace_graph.py)│ │(critical_path.py│ │(service_graph.py│
│ • Parent-Child  │ │ • Causal chain  │ │ • Dynamic edges │
│ • Self-duration │ │ • Deepest origin│ │ • Error rates   │
│ • Call depth    │ │ • Error attrs   │ │ • Node health   │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Key Capabilities:
1. **Batch Ingestion (`backend/app/telemetry/ingestion.py`)**:
   - Ingests batches of OpenTelemetry spans atomically into SQLite WAL storage.
   - Provides indexed lookups by `trace_id`, `service_name`, and timestamp.
2. **DAG Call Tree Reconstructor (`backend/app/telemetry/trace_graph.py`)**:
   - Reconstructs arbitrary-depth call hierarchies, computing self-duration ($T_{self} = T_{total} - \sum T_{children}$) and tree depth per node.
   - Defensively isolates and handles circular call references.
3. **Causal Failure Origin Pinpointing (`backend/app/telemetry/critical_path.py`)**:
   - Differentiates between root failure sources (e.g. `payment-service` DB pool exhaustion with HTTP 500) and cascading upstream error proxies (e.g. `order-service` and `gateway-service` returning HTTP 502).
   - Generates an auditable `FailureOriginReport` containing the propagation chain and error metadata.
4. **Service Dependency Graph (`backend/app/telemetry/service_graph.py`)**:
   - Analyzes trace spans across time to infer dynamic service topology nodes and directed call edges with aggregated call volume, latency, and error rates.
5. **REST API Endpoints (`backend/app/api/v1/telemetry.py`)**:
   - `POST /api/v1/telemetry/spans`: Batch span ingestion.
   - `GET /api/v1/telemetry/spans/{trace_id}`: Flat spans for a trace.
   - `GET /api/v1/telemetry/traces/{trace_id}/tree`: Reconstructed DAG call tree.
   - `GET /api/v1/telemetry/traces/{trace_id}/failure-origin`: Root failure origin isolation.
   - `GET /api/v1/telemetry/traces`: Recent trace listing.
   - `GET /api/v1/telemetry/topology`: Live service dependency graph.

---

## 6. Part 4: Autonomous Incident Detection & Causal RCA Agent

Part 4 implements the incident lifecycle detection layer, blast radius correlation engine, and the Root Cause Analysis (RCA) Hypothesis Agent:

```
┌────────────────────────────────────────────────────────┐
│             Telemetry Spans & Failure Traces           │
└────────────────────────────┬───────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│               Incident Detection Engine                │
│             (backend/app/incidents/detector.py)        │
│  • Causal failure clustering                           │
│  • Deduplication against active incidents              │
│  • Blast radius computation (upstream topology impact) │
└────────────────────────────┬───────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│                 Incident Entity (DETECTED)             │
│  • title, severity, suspect_service, blast_radius_json │
└────────────────────────────┬───────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│               RCA Hypothesis Agent                     │
│             (backend/app/agents/rca_agent.py)          │
│  • Telemetry evidence extraction                       │
│  • Deepest causal fault isolation                      │
│  • Synthesis of ranked Hypotheses                      │
│  • Generation of executable Sandbox Reproduction Recipe│
└────────────────────────────┬───────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│           Incident Status: INVESTIGATING               │
│  • Hypotheses stored with rank & reproduction recipe   │
│  • Audit event logged: HYPOTHESES_GENERATED            │
└────────────────────────────────────────────────────────┘
```

### Key Capabilities:
1. **Multi-Trace Alert Storm Correlation (`backend/app/incidents/detector.py`)**:
   - Gathers cascading errors across multiple traces and isolates the true root-cause service.
   - Correlates multi-tier errors into a single actionable `Incident` rather than triggering multiple fragmented alerts.
   - Dynamically calculates `blast_radius_json` encompassing all impacted upstream services and endpoints.
2. **Causal RCA Hypothesis Agent (`backend/app/agents/rca_agent.py`)**:
   - Analyzes trace DAGs, extracts error codes, timestamps, and span attributes (`db.pool.exhausted`, active connection counts).
   - Forms ranked, structured hypotheses explaining the distributed failure mechanism.
   - Automatically attaches an executable `reproduction_recipe` JSON to each hypothesis defining the target service, concurrency, parameters, and expected error signature for the Part 5 sandbox.
3. **State Machine Validation (`backend/app/incidents/service.py`)**:
   - Strictly enforces linear progression: `DETECTED` → `INVESTIGATING` → `REPRODUCING` → `VERIFIED` → `REMEDIATED` → `RESOLVED` → `CLOSED`.
   - Prevents illegal skips (e.g. attempting to remediate before sandbox reproduction and verification).
   - Generates an immutable, append-only `AuditEvent` log for every state transition and actor.
4. **REST API Endpoints (`backend/app/api/v1/incidents.py`)**:
   - `POST /api/v1/incidents/detect`: Triggers scan and failure correlation.
   - `GET /api/v1/incidents`: Lists incidents with status/severity filters.
   - `GET /api/v1/incidents/{incident_id}`: Comprehensive incident dossier.
   - `POST /api/v1/incidents/{incident_id}/analyze`: Triggers RCA Agent hypothesis generation.
   - `PATCH /api/v1/incidents/{incident_id}/status`: Safe state machine transition.

---

## 7. Part 5: Isolated Sandbox Execution & Empirical Verification

Part 5 implements real OS-level process sandboxing and closed-loop hypothesis verification without third-party virtualization dependencies:

```
┌────────────────────────────────────────────────────────┐
│           RCA Hypothesis (INVESTIGATING)              │
│       • reproduction_recipe JSON                       │
│       • expected_signature (e.g. 500 DBPoolExhaustion) │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Verification Agent                       │
│       (backend/app/agents/verification_agent.py)       │
└─────────────┬────────────────────────────┬─────────────┘
              │ 1. Spawn isolated runtime  │ 2. Execute recipe
              ▼                            ▼
┌───────────────────────────┐    ┌───────────────────────┐
│   ProcessSandboxRunner    │    │ ReproductionExecutor  │
│(backend/app/sandbox/runner│    │(backend/app/sandbox/  │
│          .py)             │    │    reproduction.py)   │
│ • Ephemeral temp dir      │    │ • Dynamic HTTP pool   │
│ • Dynamic port allocation │    │ • Error fingerprinting│
│ • Stripped env vars       │    │ • Latency measurement │
│ • Clean SIGTERM/SIGKILL   │    └───────────┬───────────┘
└─────────────┬─────────────┘                │
              │ Real stdout/stderr logs      │ Observed metrics
              └──────────────┬───────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│            Empirical Evidence Comparison               │
│ • Expected signature == Observed failure signature?   │
└──────────────┬───────────────────────────┬─────────────┘
               │ MATCH                     │ NO MATCH
               ▼                           ▼
┌─────────────────────────────┐ ┌────────────────────────┐
│   Hypothesis: VERIFIED      │ │   Hypothesis: REFUTED  │
│   Incident: VERIFIED        │ │   Incident:            │
│   (Proceed to remediation)  │ │   INVESTIGATING        │
└─────────────────────────────┘ └────────────────────────┘
```

### Key Capabilities:
1. **OS Process Isolation (`backend/app/sandbox/runner.py`)**:
   - `ProcessSandboxRunner` dynamically allocates ephemeral HTTP ports (starting from `TRACEHEAL_SANDBOX_BASE_PORT` or using `find_free_port`).
   - Spawns target service workers in isolated sub-processes (`sys.executable -m uvicorn ...`) with a stripped, hermetic environment and ephemeral working directory.
   - Actively polls `/health` with exponential backoff until the sandbox instance is confirmed healthy before allowing traffic.
   - Enforces clean termination (graceful SIGTERM with fallback to SIGKILL) and flushes complete execution logs to persistent storage.
2. **Deterministic Reproduction Engine (`backend/app/sandbox/reproduction.py`)**:
   - `ReproductionExecutor` parses hypothesis reproduction recipes into structured parameters: concurrency, total requests, endpoint, payload, and chaos configuration.
   - Drives real asynchronous HTTP client pools against the sandboxed service instance.
   - Analyzes response status codes, latency percentiles, and exception payloads against the expected failure signature.
3. **Hypothesis Verification Agent (`backend/app/agents/verification_agent.py`)**:
   - Compares empirical sandbox outcomes with the RCA hypothesis signature.
   - If reproduction succeeds: updates `Hypothesis.status` to `VERIFIED`, attaches empirical metrics to `SandboxRun.reproduction_verified = True`, and updates the incident state machine to `VERIFIED`.
   - If reproduction fails or disproves the premise: marks `Hypothesis.status` as `REFUTED`, records `SandboxRun.reproduction_verified = False`, and reverts the incident back to `INVESTIGATING` with an auditable explanation.
4. **REST API Endpoints (`backend/app/api/v1/sandbox.py`)**:
   - `POST /api/v1/sandbox/reproduce/{hypothesis_id}`: Triggers end-to-end sandbox creation, recipe execution, and empirical hypothesis verification.
   - `GET /api/v1/sandbox/runs/{run_id}`: Retrieves sandbox run telemetry, process execution logs, port allocation, and verification outcomes.

---

## 8. Part 6: Safe Patch Generation, Policy Verification & Shadow Remediation

Part 6 introduces closed-loop self-healing through automated policy-checked patch generation, empirical shadow validation in ephemeral sandboxes, human-in-the-loop approval gates, and zero-downtime canary deployment with automated rollback:

```
┌────────────────────────────────────────────────────────┐
│           Empirically Verified Hypothesis              │
│       • Suspect service & causal origin pinpointed     │
│       • State: VERIFIED                                │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Remediation Agent                        │
│       (backend/app/agents/remediation_agent.py)        │
│  • Synthesizes unified config diff & parameter updates │
│  • Generates symmetric rollback diff                   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Policy Verification Engine               │
│     (backend/app/remediation/policy_engine.py)         │
│  • Service allowlist                                   │
│  • Dangerous command/injection denylist                │
│  • Parameter boundary assertions                       │
│  • Diff size integrity & mandatory rollback diff       │
└───────────────────────────┬────────────────────────────┘
                            │ Status: PASSED
                            ▼
┌────────────────────────────────────────────────────────┐
│               Shadow Sandbox Validator                 │
│     (backend/app/remediation/shadow_validator.py)      │
│  • Provisions isolated sandbox instance                │
│  • Applies remediation patch via /config/remediate     │
│  • Replays original reproduction failure workload      │
│  • Proves 0% error rate & failure signature resolution │
└───────────────────────────┬────────────────────────────┘
                            │ Status: VALIDATED
                            ▼
┌────────────────────────────────────────────────────────┐
│           Human-in-the-Loop Approval Gate              │
│     • Enforces Policy=PASSED and Validation=VALIDATED  │
│     • Status: PENDING_APPROVAL → APPROVED              │
└───────────────────────────┬────────────────────────────┘
                            │ Status: APPROVED
                            ▼
┌────────────────────────────────────────────────────────┐
│            Remediation Deployer & Safe Canary          │
│        (backend/app/remediation/deployer.py)           │
│  • Deploys patch to live target service                │
│  • Runs post-apply /health check                       │
│  • If failed: triggers automated rollback immediately  │
│  • If healthy: transitions Incident to REMEDIATED      │
└────────────────────────────────────────────────────────┘
```

### Key Capabilities:
1. **Autonomous Remediation Agent (`backend/app/agents/remediation_agent.py`)**:
   - Synthesizes concrete, minimal unified configuration diffs (`diff_content`) and parameter payloads based on verified root causes.
   - Automatically couples each proposal with an exact, executable rollback diff (`rollback_diff`).
   - Dispatches the proposal directly into the policy engine upon creation and records audit trails.
2. **Deterministic Safety Policy Engine (`backend/app/remediation/policy_engine.py`)**:
   - Guardrails against arbitrary command execution, privilege escalation, shell injection patterns (`rm -rf`, `powershell`, `os.system`, `subprocess`, SQL destruction).
   - Validates strict parameter boundary ranges ($1 \le \text{max\_connections} \le 100$, $0.01 \le \text{timeout} \le 30.0$).
   - Enforces service boundary allowlists and mandatory rollback diff existence.
3. **Shadow Sandbox Verification (`backend/app/remediation/shadow_validator.py`)**:
   - Validates proposed patches inside isolated sandboxes *before* production deployment.
   - Proves empirically that the failure signature is eliminated and error rate drops to 0.0% under identical contention.
4. **Approval Gate & Deployment Orchestrator (`backend/app/remediation/deployer.py`)**:
   - Strictly validates that only proposals that have `policy_check_status == "PASSED"` and `validation_status == "VALIDATED"` can be approved.
   - Safe canary deployment against target microservices with post-deployment `/health` verification and automatic rollback safety.
   - Advances incident lifecycle state machine from `VERIFIED` to `REMEDIATED`.
5. **REST API Endpoints (`backend/app/api/v1/remediations.py`)**:
   - `POST /api/v1/remediations/propose/{incident_id}`: Synthesizes remediation from verified hypothesis.
   - `POST /api/v1/remediations/{remediation_id}/policy-check`: Re-evaluates security policy.
   - `POST /api/v1/remediations/{remediation_id}/shadow-validate`: Executes isolated sandbox shadow validation.
   - `POST /api/v1/remediations/{remediation_id}/approve`: Submits human approval/rejection.
   - `POST /api/v1/remediations/{remediation_id}/apply`: Deploys approved remediation to live service.
   - `POST /api/v1/remediations/{remediation_id}/rollback`: Executes manual rollback if needed.
   - `GET /api/v1/remediations/{remediation_id}`: Retrieves remediation dossier.
   - `GET /api/v1/remediations/incident/{incident_id}`: Lists remediations for an incident.

---

## 9. Part 7: Post-Incident Dossier, PR Generator & Postmortem Engine

Part 7 closes the incident lifecycle by validating full production baseline recovery, generating rich SRE postmortem reports, formulating automated Git Pull Requests with verified patches, and providing final incident sign-off and closure:

```
┌────────────────────────────────────────────────────────┐
│               Incident State: REMEDIATED               │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Recovery Validator                       │
│    (backend/app/postmortem/recovery_validator.py)      │
│  • Dispatches baseline checkout transactions           │
│  • Confirms 0% error rate & cluster recovery           │
│  • Transitions state: REMEDIATED → RESOLVED            │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│             Postmortem & PR Engines                    │
│   ┌────────────────────────┐  ┌─────────────────────┐  │
│   │  PostmortemGenerator   │  │ PullRequestGenerator│  │
│   │(postmortem/generator.py│  │ (postmortem/pr_     │  │
│   │                        │  │     generator.py)   │  │
│   │ • MTTD & MTTR metrics  │  │ • Git branch ref    │  │
│   │ • Root Cause Analysis  │  │ • Patch file (.patch│  │
│   │ • Empirical sandbox run│  │ • SRE verification  │  │
│   │ • Shadow benchmarks    │  │   checklist         │  │
│   │ • Chronological table  │  │ • Rollback diff     │  │
│   │ • P0/P1/P2 action items│  │ • Commit hash ref   │  │
│   └────────────────────────┘  └─────────────────────┘  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│           Final Incident Sign-Off & Closure            │
│       • Formally marks state: RESOLVED → CLOSED        │
│       • Records closed_at timestamp & executive audit  │
└────────────────────────────────────────────────────────┘
```

### Key Capabilities:
1. **Cluster Recovery Validator (`backend/app/postmortem/recovery_validator.py`)**:
   - Executes live end-to-end checkout traffic across microservice endpoints.
   - Validates that error rate is 0.0% post-remediation.
   - Advances incident lifecycle state machine from `REMEDIATED` to `RESOLVED` and sets `resolved_at`.
2. **Automated Postmortem Engine (`backend/app/postmortem/generator.py`)**:
   - Synthesizes professional SRE Post-Incident Reviews formatted in Markdown and structured JSON.
   - Extracts MTTD ($T_{detect} - T_{telemetry\_origin}$) and MTTR ($T_{applied} - T_{detect}$).
   - Integrates empirical sandbox proof (port, exit code, error signature) and shadow validation benchmark metrics.
   - Generates a chronological incident timeline table from immutable audit events.
   - Formulates prioritized preventative action items (P0, P1, P2) for infrastructure and reliability teams.
3. **Automated Git Pull Request Generator (`backend/app/postmortem/pr_generator.py`)**:
   - Generates feature branches (e.g. `traceheal/fix-payment-service-3832f37a`), PR titles, and comprehensive Markdown bodies for GitHub/GitLab.
   - Exports unified diffs as standalone `.patch` files into the `patches/` repository directory.
   - Populates SRE verification checklists and attaches verified rollback diffs.
4. **Lifecycle Closure Orchestrator (`backend/app/postmortem/service.py`)**:
   - Strictly enforces that only `RESOLVED` incidents can be closed.
   - Stamps `closed_at` and records the final `INCIDENT_CLOSED` audit record.
5. **REST API Endpoints (`backend/app/api/v1/postmortem.py`)**:
   - `POST /api/v1/postmortem/{incident_id}/validate-recovery`: Validates cluster health and advances state to `RESOLVED`.
   - `POST /api/v1/postmortem/{incident_id}/generate`: Synthesizes Markdown and JSON postmortem.
   - `POST /api/v1/postmortem/{incident_id}/create-pr`: Formulates Pull Request dossier and patch file.
   - `POST /api/v1/postmortem/{incident_id}/close`: Formally closes resolved incident.
   - `GET /api/v1/postmortem/{incident_id}`: Retrieves existing postmortem and PR data.

---

## 10. Part 8: Real-Time Event Streaming & Live Agent Terminal SSE

Part 8 establishes the zero-polling, real-time reactive event streaming backbone. It broadcasts agent cognitive thought steps, empirical sandbox logs, telemetry spikes, and state transitions directly to the browser UI via standard Server-Sent Events (SSE):

```
┌────────────────────────────────────────────────────────┐
│               Event Emitters & Hooks                   │
│   • RCA Agent (agent:thought)                          │
│   • Verification Agent (agent:action)                  │
│   • Sandbox Process Logs (sandbox:stdout / stderr)     │
│   • Telemetry Ingestion (telemetry:spike)              │
│   • Incident Lifecycle (incident:state)                │
└───────────────────────────┬────────────────────────────┘
                            │ emit_*()
                            ▼
┌────────────────────────────────────────────────────────┐
│              Asynchronous Pub/Sub Event Bus            │
│                 (backend/app/events/bus.py)            │
│  • Wildcard pattern routing (agent:*, incident:*, *)   │
│  • Ring buffer replay memory (last 300 events)         │
│  • Backpressure management & overflow protection       │
│  • Incident-specific subscriber filtering              │
└──────────────┬───────────────────────────┬─────────────┘
               │                           │
               ▼                           ▼
┌─────────────────────────────┐ ┌────────────────────────┐
│  SSE Universal Stream       │ │  Incident Terminal SSE │
│  GET /api/v1/stream/events  │ │GET /api/v1/stream/     │
│                             │ │    incidents/{id}      │
│ • Replays last N events     │ │ • Real-time CLI logs   │
│ • Live agent thought stream │ │ • Agent tool actions   │
│ • Heartbeat keepalive ping  │ │ • Disconnect detection │
└─────────────────────────────┘ └────────────────────────┘
```

### Key Capabilities:
1. **Asynchronous Event Bus (`backend/app/events/bus.py`)**:
   - High-throughput coroutine Pub/Sub hub with wildcard topic subscriptions (`agent:*`, `incident:*`, `sandbox:*`, `telemetry:*`, `system:*`).
   - In-memory ring buffer (default 300 events) enabling instant state replay for newly connected or reconnecting UI clients (`replay_last=N`).
   - Backpressure-aware subscriber queues with FIFO dropping to prevent memory bloat from slow network consumers.
2. **Standardized W3C SSE Streamer (`backend/app/events/streaming.py`)**:
   - Formats events according to W3C `text/event-stream` specification (`id`, `event`, `data`).
   - Emits automatic `: ping\n\n` comments to prevent reverse proxy and load balancer socket timeouts.
   - Monitors client disconnects (`request.is_disconnected()`) to guarantee clean teardown of consumer queues.
3. **Cognitive Reasoning & Log Hooks (`backend/app/events/hooks.py`)**:
   - `emit_agent_thought`: Broadcasts fine-grained thought steps (`AGENT_THINKING`) with reasoning metadata.
   - `emit_agent_action`: Broadcasts operational decisions (`AGENT_ACTION`) such as launching sandboxes or testing patches.
   - `emit_sandbox_log`: Streams raw sandbox stdout/stderr log lines directly to UI terminals.
   - `emit_incident_state_change`: Emits instant push notifications whenever the incident state machine transitions.
   - `emit_telemetry_spike` & `emit_system_vital`: Streams metrics and anomalies.
4. **REST API Streaming Endpoints (`backend/app/api/v1/stream.py`)**:
   - `GET /api/v1/stream/events`: Universal SSE stream with topic, incident, and replay filtering.
   - `GET /api/v1/stream/incidents/{incident_id}`: Dedicated incident investigation terminal stream.
   - `GET /api/v1/stream/metrics`: Real-time system vitals and telemetry spikes.
   - `POST /api/v1/stream/publish`: Programmatic event publishing endpoint for manual hooks and simulators.
   - `GET /api/v1/stream/history`: Ring-buffer history inspection.

---

## 11. Part 9: Real-Time Visual SRE Command Center (Single-Page Frontend Application)

Part 9 delivers a comprehensive, responsive, dark-mode (OLED) Single-Page Application (SPA) designed for Site Reliability Engineers (SREs). It unifies real-time distributed telemetry, dynamic dependency visualization, live agent reasoning, and autonomous self-healing into an interactive command cockpit:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   TraceHeal SRE Command Center (HTML5 / CSS / Vanilla JS)             │
├────────────────────────────────────────┬───────────────────────────────────────────────┤
│  Top Navigation & Live HUD             │ • SSE Connection Pulse Dot & Keepalive Pings  │
│                                        │ • Active Incidents, MTTR & Availability Cards │
│                                        │ • One-Click "Simulate Incident" Action Trigger│
├────────────────────────────────────────┴───────────────────────────────────────────────┤
│  1. Interactive Cluster Topology       • Live SVG Directed Graph (Gateway, Order, etc.)│
│     & Service Dependency Map           • Animated Bezier Curves with Live Latency Badges│
│                                        • Service Node Inspector (Health, Vitals, Ports) │
├────────────────────────────────────────┼───────────────────────────────────────────────┤
│  2. Incident Triage Dossier            • Stepped State Machine Tracker (DETECTED → ...)│
│     & Lifecycle Progression            • Root Cause Analysis (RCA) Diagnostic Cards    │
│                                        • Operator Action Bar: RCA, Patch, Canary, Close │
├────────────────────────────────────────┼───────────────────────────────────────────────┤
│  3. Live Agent Cognitive Terminal      • Zero-polling EventSource SSE to /stream/events│
│                                        • Color-coded Event Categories (Thought, Action)│
│                                        • Category Filtering, Auto-Scroll & Ring Replay │
├────────────────────────────────────────┼───────────────────────────────────────────────┤
│  4. Shadow Sandbox & Diff Inspector    • High-Fidelity Unified Diff Code Inspector     │
│                                        • 5-Rule Safety Policy Checklist (AST, Deadlock)│
│                                        • Empirical Sandbox Stress Test Benchmarks      │
├────────────────────────────────────────┼───────────────────────────────────────────────┤
│  5. Chaos & Control Center             • Programmatic Chaos Injections (Pool, Latency) │
│                                        • End-to-End Autonomous Simulation Runner       │
│                                        • Cluster Baseline Health Restoration           │
└────────────────────────────────────────┴───────────────────────────────────────────────┘
```

### Key Capabilities:
1. **Responsive Dark-Theme Architecture (`frontend/css/style.css`, `frontend/index.html`)**:
   - Implements an OLED dark cyber design system with CSS custom property tokens (`#060911` root, `#111a2e` card surfaces).
   - Fully responsive across desktop, tablet, and mobile views; respects `prefers-reduced-motion`.
   - Adheres to WCAG 2.1 accessibility guidelines with high text contrast ratios ($\ge 4.5:1$).
2. **Dynamic SVG Service Topology Renderer (`frontend/js/topology.js`)**:
   - Renders the microservice DAG (`gateway-service`, `order-service`, `payment-service`, `inventory-service`).
   - Animates flowing dashed lines along active request paths, color-coding edges based on latency spikes and error status.
   - Provides an interactive Node Inspector displaying per-service status, latencies, error percentages, and sandbox isolation modes.
3. **Autonomous Incident Lifecycle Tracker & Dossier (`frontend/js/app.js`)**:
   - Tracks the full 7-stage incident progression: `DETECTED` $\to$ `INVESTIGATING` $\to$ `REPRODUCING` $\to$ `VERIFIED` $\to$ `REMEDIATED` $\to$ `RESOLVED` $\to$ `CLOSED`.
   - Provides interactive controls to execute each step of the autonomous loop: "Run RCA Agent", "Propose Safe Patch", "Verify in Sandbox", "Deploy Canary", "Rollback", and "Resolve & Close".
4. **Live Cognitive Terminal Streaming Component**:
   - Connects directly to `/api/v1/stream/events` with reconnection handling and heartbeat tracking.
   - Categorizes messages by category: Agent Thoughts (Cyan), Agent Actions (Amber), Incident State Transitions (Emerald/Crimson), Telemetry Spikes (Blue), and Sandbox Stress Logs (Purple).
   - Supports real-time filtering, sticky auto-scrolling, terminal clearing, and 100-event history replay from the ring buffer.
5. **Shadow Diff Viewer & Safety Policy Checklist**:
   - Displays syntax-highlighted unified patch diffs with line numbering and addition/deletion formatting.
   - Evaluates the 5 Automated Safety Policy checks (AST & Syntax, Resource Limits, Deadlock Guard, Idempotency, Security Boundary).
   - Shows empirical sandbox benchmark comparisons (e.g. 100% Failure / 2480ms baseline vs 0% Failure / 38ms verified).
6. **Chaos Injection & Control Center API (`backend/app/api/v1/chaos.py`)**:
   - `GET /api/v1/chaos/status`: Probes microservice cluster nodes and returns operational health.
   - `POST /api/v1/chaos/inject`: Triggers programmatic failure scenarios and emits telemetry alerts.
   - `POST /api/v1/chaos/reset`: Restores all services to nominal baseline.
   - `POST /api/v1/chaos/simulate-incident`: Synthesizes cascading failure traces, detects incidents, and streams live events to the Command Center with one click.
7. **FastAPI Web Asset Hosting (`backend/app/main.py`)**:
   - Mounts `/static` for assets and `/patches` for downloadable patch files.
   - Serves `frontend/index.html` at both `/` and `/ui`.

---

## 12. Part 10: End-to-End Autonomous Lifecycle Orchestration, Production CLI & Containerization

Part 10 represents the capstone of the TraceHeal platform. It unifies all independent subsystems (Telemetry Ingestion, RCA Reasoning Agent, Empirical Sandbox Isolation, AST Patch Synthesis, Policy Gating, Canary Deployment, Baseline Recovery, and Postmortem PR Generation) into an autonomous, closed-loop orchestrator with zero human intervention required, complete with a production-ready Click CLI and multi-container Docker Compose packaging:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               TRACEHEAL END-TO-END AUTONOMOUS SELF-HEALING CLOSED LOOP                 │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
    ┌───────────────────────────────────────┴───────────────────────────────────────┐
    ▼                                                                               ▼
[REST API: POST /api/v1/orchestrator/run-cycle]                         [CLI: traceheal auto-heal]
    │                                                                               │
    └───────────────────────────────────────┬───────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        AutonomousLifecycleOrchestrator                                 │
│                     (backend/app/orchestrator/lifecycle.py)                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ [1/7] Ingest & Detect (DETECTED)      • Ingests telemetry spikes, triggers detector    │
│ [2/7] RCA Diagnostic (INVESTIGATING)  • Traverses call graph, ranks root-cause hyp.    │
│ [3/7] Empirical Sandbox (REPRODUCING) • Clones code, reproduces failure deterministically│
│ [4/7] Policy & Verification (VERIFIED)• Synthesizes diff, validates 5 safety policies  │
│ [5/7] Canary Rollout (REMEDIATED)     • Deploys 10% canary traffic with 0 regressions  │
│ [6/7] Baseline Recovery (RESOLVED)    • Replays synthetic checkouts, confirms recovery │
│ [7/7] Postmortem & PR (CLOSED)        • Formulates Git branch, .patch file & PIR dossier│
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       Production Packaging & Deployment Runtime                        │
├────────────────────────────────────────┬───────────────────────────────────────────────┤
│ • Production Click CLI (cli/main.py)   │ • Container Architecture (Dockerfile)         │
│   - traceheal version                  │   - Multi-stage Python 3.12-slim base         │
│   - traceheal auto-heal / demo         │   - Non-root UID 1000 'traceheal' security    │
│   - traceheal incident list / inspect  │   - Automated Docker curl healthchecks        │
│   - traceheal postmortem <id>          │ • Docker Compose Mesh (docker-compose.yml)    │
│   - traceheal cluster status           │   - Core engine + 4 microservices + volumes   │
│   - traceheal start                    │   - Persistent volumes for data/ and patches/ │
└────────────────────────────────────────┴───────────────────────────────────────────────┘
```

### Key Capabilities:
1. **Autonomous Closed-Loop Orchestrator (`backend/app/orchestrator/lifecycle.py`)**:
   - Executes the complete 7-stage self-healing lifecycle deterministically:
     - **Phase 1 (`DETECTED`)**: Ingests distributed telemetry traces and triggers `IncidentDetector`.
     - **Phase 2 (`INVESTIGATING`)**: Engages `RCAAgent` to traverse call graph topology and formulate ranked hypotheses.
     - **Phase 3 (`REPRODUCING`)**: Instantiates isolated sandbox environments to empirically reproduce faults.
     - **Phase 4 (`VERIFIED`)**: Formulates surgical configuration/code diffs and validates against the 5-rule Safety Policy Engine.
     - **Phase 5 (`REMEDIATED`)**: Deploys canary rollouts (10% traffic weighting) with 0 regressions.
     - **Phase 6 (`RESOLVED`)**: Dispatches synthetic traffic via `RecoveryValidator` to confirm 0.0% error rate.
     - **Phase 7 (`CLOSED`)**: Automatically synthesizes Markdown Post-Incident Review dossiers and generates Git Pull Request branches with exported `.patch` files.
   - Emits real-time SSE cognitive stream updates (`emit_agent_thought`, `emit_agent_action`, `emit_incident_state_change`) at every phase transition.

2. **Autonomous Orchestration REST API (`backend/app/api/v1/orchestrator.py`)**:
   - `POST /api/v1/orchestrator/run-cycle`: Accepts `scenario`, `target_service`, and `trace_count`, running the full closed-loop sequence asynchronously and returning complete incident manifests.

3. **Production Click CLI Tool (`cli/main.py`)**:
   - Registered as console script `traceheal` via `pyproject.toml`.
   - Commands:
     - `traceheal version`: Displays platform version, environment, database URI, and configuration.
     - `traceheal start [--host] [--port]`: Starts the FastAPI server and SRE Command Center dashboard.
     - `traceheal auto-heal [--scenario] [--target-service] [--trace-count]`: Executes the complete closed-loop self-healing sequence in the terminal with colored ASCII output.
     - `traceheal demo`: Alias for `traceheal auto-heal` demonstration.
     - `traceheal incident list [--limit]`: Tabulates all recorded incidents, status, severity, and impacted services.
     - `traceheal incident inspect <id>`: Displays comprehensive incident details and timeline.
     - `traceheal postmortem <id>`: Renders the full Markdown Post-Incident Review (PIR) report directly in the console.
     - `traceheal cluster status`: Checks HTTP health across the 4 microservices.

4. **Production Multi-Stage Docker & Compose Packaging (`Dockerfile`, `docker-compose.yml`)**:
   - `Dockerfile`: Minimalist `python:3.12-slim` container, non-root user `traceheal` (UID 1000), healthchecked via `curl -f http://localhost:8000/api/v1/health`.
   - `docker-compose.yml`: Coordinates the complete microservice mesh (`traceheal-core`, `gateway-service`, `order-service`, `payment-service`, `inventory-service`) on bridge network `traceheal-net` with persistent storage for `data/` and `patches/`.







