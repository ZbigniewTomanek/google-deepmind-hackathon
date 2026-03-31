# Test Episodes: Project Titan

Two agents — Alice (backend engineer) and Bob (ML engineer) — contributing knowledge
about the same project. Episodes are designed with intentional overlap to exercise
entity deduplication and knowledge merging.

## Shared Entities (Expected Dedup Targets)

These entities appear in episodes from BOTH agents:

| Entity | Type | Alice refs | Bob refs |
|--------|------|-----------|----------|
| Project Titan | Project | EP-A1, EP-A2, EP-A3 | EP-B1, EP-B2, EP-B4 |
| Sarah Chen | Person | EP-A1 | EP-B1 |
| Marcus Rivera | Person | EP-A1 | EP-B2 |
| Kubernetes | Technology | EP-A3 | EP-B4 |
| PostgreSQL | Technology | EP-A2 | EP-B3 |

---

## Alice's Episodes (Backend Architecture)

### EP-A1: Team & Project Overview

```
Project Titan is a distributed data pipeline platform being built by our team at Meridian Labs.
Sarah Chen is the project manager — she runs the weekly standups and tracks our OKRs.
Marcus Rivera is a senior data engineer who handles the ETL orchestration layer.
I (Alice) am responsible for the backend services: the API gateway, authentication service,
and the core data processing engine. The project started in January 2026 and the initial
MVP is targeting Q3 2026 delivery. We have a team of 8 engineers split between backend,
ML, and platform infrastructure.
```

### EP-A2: Database Architecture

```
For Project Titan's storage layer, we chose PostgreSQL 16 as the primary transactional
database. The schema design uses a multi-tenant architecture with row-level security for
client data isolation. We also use TimescaleDB extension for time-series metrics storage.
The read replicas are set up with streaming replication — currently 2 replicas behind a
PgBouncer connection pool. Marcus Rivera designed the initial schema and I extended it
with the audit trail tables. We evaluated CockroachDB but PostgreSQL won on operational
simplicity and the team's existing expertise.
```

### EP-A3: Infrastructure & Deployment

```
Project Titan runs on Kubernetes (EKS on AWS). The deployment uses Helm charts with
ArgoCD for GitOps-style continuous delivery. Each microservice has its own namespace:
titan-api, titan-processor, titan-scheduler. The API gateway is built on Kong with
custom authentication plugins. We use Prometheus and Grafana for monitoring, with
PagerDuty alerting for production incidents. The CI pipeline runs on GitHub Actions
with Trivy security scanning on every PR.
```

### EP-A4: Observability & Operations

```
Our observability stack for Project Titan includes OpenTelemetry for distributed tracing,
Loki for log aggregation, and Grafana dashboards. I built a custom health check endpoint
that validates all downstream dependencies (PostgreSQL, Redis, Kafka consumers). The SLO
target is 99.9% uptime for the API gateway. We do weekly chaos engineering exercises
using LitmusChaos to test fault tolerance. The on-call rotation is shared between me,
Marcus, and two platform engineers.
```

### EP-A5: API Design & Authentication

```
The Project Titan API follows REST conventions with OpenAPI 3.1 specs. Authentication
uses OAuth 2.0 with Auth0 as the identity provider. API keys are used for service-to-service
communication, stored in AWS Secrets Manager. Rate limiting is implemented at the Kong
gateway layer — 1000 req/min for standard tier, 10000 for enterprise. We use API versioning
via URL path (v1, v2) and maintain backward compatibility for 6 months after deprecation.
The API documentation is auto-generated from the OpenAPI spec and hosted on a developer portal.
```

---

## Bob's Episodes (ML Pipeline)

### EP-B1: Project Context & ML Goals

```
I'm Bob, the ML lead on Project Titan at Meridian Labs. Our goal is to build an intelligent
data quality and feature engineering pipeline. Sarah Chen manages the project — she's great
at balancing the ML team's research needs with the engineering deadlines. The ML team has
3 people: me, Priya Patel (junior ML engineer), and a part-time research consultant.
We're building models for anomaly detection in data streams, automated feature selection,
and data drift monitoring. The whole project targets Q3 2026 for the MVP launch.
```

### EP-B2: Feature Engineering Pipeline

```
The feature engineering pipeline for Project Titan uses a multi-stage architecture.
Raw data flows through a validation layer (Great Expectations), then into feature
transformers built with Feast as the feature store. Marcus Rivera helped integrate
the feature store with the backend ETL pipeline — his Airflow DAGs feed our feature
computation jobs. We use PySpark for batch feature computation and Flink for real-time
features. The model registry is MLflow, deployed alongside the Titan ML services.
Each feature has lineage tracking back to the source dataset.
```

### EP-B3: Data Quality Framework

```
For data quality in Project Titan, we built a custom validation framework on top of
Great Expectations and dbt tests. The framework connects to PostgreSQL to validate
schema constraints, statistical distributions, and cross-table referential integrity.
Quality metrics are stored in a dedicated metrics schema and visualized in Grafana.
When data quality drops below thresholds, alerts fire to the ML team's Slack channel.
We track 47 quality dimensions across 12 data sources. Priya Patel owns the quality
dashboard and runs the weekly data health review.
```

### EP-B4: Model Training Infrastructure

```
Model training for Project Titan runs on Kubernetes GPU nodes (NVIDIA A100s).
We use Kubeflow Pipelines for ML workflow orchestration, with each training run
tracked in MLflow. The training data pipeline reads from the feature store (Feast)
and applies time-based train/test splits to prevent data leakage. Our primary model
is an XGBoost ensemble for anomaly detection, with a transformer-based model for
sequence pattern recognition. Training runs are scheduled nightly via Argo Workflows
on the same Kubernetes cluster as the backend services.
```

### EP-B5: Model Serving & Monitoring

```
ML model serving in Project Titan uses Seldon Core on Kubernetes for real-time inference.
The serving layer exposes gRPC endpoints for low-latency prediction requests. Model
monitoring tracks prediction drift using Evidently AI — when distribution shift exceeds
thresholds, the model is automatically retrained. A/B testing is implemented with Istio
service mesh traffic splitting. We serve approximately 50,000 predictions per day with
a P99 latency target of 200ms. The shadow mode deployment lets us test new models against
production traffic without affecting users.
```
