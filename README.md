# TraceHeal | Autonomous SRE Command Center

> **Autonomous Incident Investigation & Shadow-Verified Self-Healing Platform for Distributed Microservices.**

[![Status](https://img.shields.io/badge/status-production--ready-emerald.svg)](https://github.com/pyharshcodes/TraceHeal)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-4%2F4%20passing-brightgreen.svg)]()

---

## ⚡ Overview

**TraceHeal** transitions cloud observability from *passive alerting* to *active, closed-loop autonomous healing*. When cascading failures strike a distributed microservice cluster, TraceHeal:
1. Detects anomalies in real-time via RFC/W3C-compliant OpenTelemetry (OTLP/HTTP) streams ($<1.8\text{s}$ MTTD).
2. Traverses the causal trace DAG to isolate the true Root Cause from cascading symptoms.
3. Scientifically reproduces the failure in an isolated sandbox runner.
4. Synthesizes surgical code/config remediations with Abstract Syntax Tree (AST) security guardrails.
5. Benchmarks and verifies the patch in a shadow runner under live burst traffic.
6. Executes zero-downtime canary rollout with automated rollback safety.
7. Publishes an auditable Postmortem Dossier and opens a verified GitHub Pull Request.

---

## 🚀 Quick Start

### 1. Local Setup
```bash
# Clone the repository
git clone https://github.com/pyharshcodes/TraceHeal.git
cd TraceHeal

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Start TraceHeal Core API & Dashboard
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in your browser.

### 2. Multi-Tier Microservices Cluster
```bash
python -m target_services.cluster
```
Spawns 6 microservices:
- `gateway-service` (Port 8080)
- `order-service` (Port 8081)
- `payment-service` (Port 8082)
- `inventory-service` (Port 8083)
- `auth-service` (Port 8084)
- `notification-service` (Port 8085)

---

## 🐳 Docker Deployment (Render / Cloud)

```bash
docker build -t traceheal:latest .
docker run -p 8000:8000 traceheal:latest
```

---

## 🛠️ Tech Stack & Standards

- **Core:** FastAPI, Python 3.11+, SQLAlchemy, aiosqlite, Pydantic v2
- **Telemetry:** OpenTelemetry Protocol (OTLP/HTTP), W3C Trace Context (`traceparent`)
- **Frontend:** Vanilla CSS & JS with Cyber Glassmorphism, Responsive SVG Service Topology, Real-Time Telemetry Radar
- **Safety:** Python AST parsing, Shadow Sandbox Runner, Canary Automated Rollback
- **Integrations:** GitHub Pull Requests, Slack webhooks, PagerDuty

---

## 📄 License
MIT License. Built for High-Performance Enterprise Reliability.
