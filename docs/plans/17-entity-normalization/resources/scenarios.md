# E2E Test Scenarios

Episodes to replay for validation (Stage 6). These are the same episodes used
in Plan 15 and Plan 16.5, ensuring consistent measurement.

## Baseline Episodes

### Episode 1: Team establishment
```
Team Atlas is working on Project Nexus, a next-generation data processing platform.
The team consists of Maya Chen (Tech Lead), Jonas Weber (Backend Engineer),
and Sarah Kim (Data Pipeline Specialist). They use DataForge as their primary
data transformation tool. The project launch is targeted for June 2025.
```

### Episode 2: Maya's role change
```
Maya Chen has been promoted from Tech Lead to Engineering Director, effective
immediately. She will continue overseeing Project Nexus but with expanded
responsibilities across the engineering organization.
```

### Episode 3: Technology migration
```
DataForge has completed its migration from Apache Kafka to Apache Pulsar for
event streaming. The migration was driven by Pulsar's superior partition
ordering guarantees and multi-tenancy support.
```

### Episode 4: Deadline change
```
The Project Nexus launch date has been moved from June 2025 to August 1, 2025.
The delay is due to new compliance requirements that must be addressed before
the public release.
```

### Episode 5: Kafka reversion
```
After evaluation, the Pulsar migration has been cancelled. DataForge is reverting
to Apache Kafka for event streaming. The team found that Kafka's ecosystem
maturity outweighed Pulsar's technical advantages.
```

### Episode 6: Team change
```
Jonas Weber has transitioned to the Security team effective this week.
Sarah Kim is replacing him as the primary backend engineer on Project Nexus.
```

### Episode 7: Precision correction
```
The NLP model precision for DataForge was previously reported as 87%.
After re-evaluation with the updated test suite, the actual measured
precision is 94.2%, a significant improvement over the initial estimate.
```

### Episode 8: Architecture evolution
```
DataForge now uses a microservices architecture consisting of:
- API Gateway for request routing and rate limiting
- Service Mesh (Istio) for inter-service communication
- Event Bus (Kafka) for async message processing
- Data Lake for long-term storage and analytics
```

## Stress Test

### Episode 9–18: Recall stress (10 recalls)
```
recall(query="Team Atlas members")
```
Run 10 times with 2-second intervals. Record max edge weight after each recall.

## Scoring Criteria

- **Acceptable**: Correct behavior, useful result
- **Partial**: Works but with caveats (minor issues, slightly off)
- **FAIL**: Fundamentally wrong or broken
