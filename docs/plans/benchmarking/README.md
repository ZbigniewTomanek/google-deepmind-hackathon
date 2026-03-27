# Benchmarking Overview

## What This Area Is For

This directory contains the benchmarking roadmap for NeoCortex.

The purpose of the benchmarking work is to give NeoCortex a trustworthy, repeatable way to measure memory performance on real external benchmarks, compare results over time, and preserve enough failure evidence to guide system improvements.

## What The Harness Is

The harness is the benchmarking system built around NeoCortex.

NeoCortex is the system under test. The harness is the code that:
- downloads and loads benchmark datasets,
- ingests benchmark data into NeoCortex,
- runs retrieval and answer generation,
- evaluates answers,
- records results and failures,
- supports repeatable reruns and resume.

In this project, the harness is planned to live under `benchmarks/` at the repository root.

## End Goal

The end goal is not just to add benchmark code. It is to make it possible to answer three questions with evidence:

- What score does NeoCortex achieve on a real long-term memory benchmark when run correctly?
- Can that score be reproduced later against newer NeoCortex revisions using the same dataset and method?
- When NeoCortex fails, do we have enough preserved evidence to understand why and improve the system deliberately?

When the Stage 1 work is complete, an operator should be able to run a benchmark command, produce believable report artifacts, inspect failures, and use the output as a real baseline for future NeoCortex work.

## Stage Map

### Stage 1: Skeleton And LongMemEval

Build the initial benchmarking harness and make LongMemEval-S run correctly against NeoCortex.

This stage establishes:
- the `benchmarks/` package,
- dataset download and parsing,
- the NeoCortex adapter,
- the benchmark runner,
- answer and judge evaluation,
- report generation,
- smoke and validation tests.

This is the foundation stage. Its purpose is to create a correct and reusable benchmark capability, not just a one-off script.

### Stage 2: LoCoMo

Extend the harness to support LoCoMo and report both F1 and LLM-as-judge results.

This stage broadens benchmark coverage and improves comparability with other memory systems that report LoCoMo results.

### Stage 3: MemoryBench Adapter

Integrate NeoCortex with `supermemoryai/memorybench`.

This stage makes it possible to run NeoCortex through the same external benchmarking framework used for competitor comparisons and MemScore-style reporting.

### Stage 4: ConvoMem And Diagnostics

Add ConvoMem plus NeoCortex-specific diagnostics.

This stage goes beyond standard benchmark scores and starts measuring graph-specific strengths and weaknesses such as:
- entity resolution,
- relationship extraction quality,
- temporal correctness,
- multi-hop retrieval and reasoning behavior.

## Why Stage 1 Matters

Stage 1 is the enabling step for everything else.

Without a correct harness, later benchmark coverage and competitor comparisons are not trustworthy. Stage 1 creates the baseline infrastructure that later stages reuse.

## Key Files

- [Plan 07](./07-benchmarking-plan.md)
- [Ways Of Working](./WAYS_OF_WORKING.md)
- [Stage 1 Ralph Plan](./07a-stage1-ralph-plan/README.md)
