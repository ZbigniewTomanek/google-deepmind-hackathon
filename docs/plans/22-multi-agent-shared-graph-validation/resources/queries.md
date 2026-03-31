# Recall Queries

10 queries designed to test cross-agent knowledge retrieval. Each query targets
specific knowledge that one or both agents contributed.

## Query Table

| # | Query Text | Expected Source Agent | Cross-Agent Test |
|---|------------|----------------------|-----------------|
| Q1 | "What database does Project Titan use for storage?" | Alice (EP-A2: PostgreSQL 16, TimescaleDB, PgBouncer) | Bob should recall alice's DB knowledge |
| Q2 | "What ML model is used for anomaly detection?" | Bob (EP-B4: XGBoost ensemble, transformer) | Alice should recall bob's ML knowledge |
| Q3 | "Who is the project manager for Titan?" | Both (EP-A1, EP-B1: Sarah Chen) | Dedup test — single answer expected |
| Q4 | "How is the API gateway architected?" | Alice (EP-A3: Kong, custom auth plugins) | Bob should recall alice's infra knowledge |
| Q5 | "What data quality metrics are tracked?" | Bob (EP-B3: 47 dimensions, 12 sources, Great Expectations) | Alice should recall bob's quality framework |
| Q6 | "What is the MVP delivery timeline?" | Both (EP-A1, EP-B1: Q3 2026) | Cross-agent temporal info |
| Q7 | "How is Kubernetes used in the project?" | Both (EP-A3: EKS/ArgoCD, EP-B4: GPU nodes/Kubeflow) | Merged infra knowledge |
| Q8 | "What is Marcus Rivera's role?" | Both (EP-A1: senior data eng/ETL, EP-B2: ETL/Airflow/feature store) | Person entity dedup |
| Q9 | "Describe the data ingestion pipeline" | Bob (EP-B2: Great Expectations→Feast→PySpark/Flink) | Alice should recall bob's pipeline |
| Q10 | "What monitoring and observability tools are used?" | Alice (EP-A4: OpenTelemetry, Loki, Grafana, PagerDuty) | Bob should recall alice's ops stack |

## Scoring Rubric

For each query, score as:

- **PASS**: At least one result in top 5 contains information from the "other" agent
  (i.e., when run as alice, result contains bob's knowledge; vice versa)
- **PARTIAL**: Results are relevant but only from the querying agent's own contributions
- **FAIL**: No relevant results, or results from wrong domain entirely

## Result Recording Template

```
Query Q_: "<query text>"
Agent: alice / bob

| Pos | Name | Score | Activation | Content Preview |
|-----|------|-------|------------|-----------------|
| 1   |      |       |            |                 |
| 2   |      |       |            |                 |
| 3   |      |       |            |                 |

Cross-agent content found: YES / NO
Verdict: PASS / PARTIAL / FAIL
```
