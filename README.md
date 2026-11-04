# Job Market Intelligence Pipeline

[![Tests](https://github.com/esrakiv/job-market-intelligence/actions/workflows/tests.yml/badge.svg)](https://github.com/esrakiv/job-market-intelligence/actions/workflows/tests.yml)

A multi-source data pipeline that collects, normalizes, deduplicates, and
evaluates data engineering and analytics engineering vacancies.

It was built as a personal decision-support tool, using deterministic and
inspectable rules to assign `APPLY`, `REVIEW`, or `SKIP` decisions.

## Sources

- Jobicy remote-job API
- Arbeitnow job-board API
- Jobindex search and detail pages

Jobicy and Arbeitnow are auxiliary sources. Jobindex is the main Denmark source.
The pipeline deliberately fails when Jobindex search is unavailable instead of
silently reporting an incomplete run as successful.

## Pipeline

```mermaid
flowchart LR
    A[Jobicy API] --> D[Source ingestion]
    B[Arbeitnow API] --> D
    C[Jobindex search and detail pages] --> D

    S[Airflow schedule] -. triggers .-> D

    D --> E[Raw JSON snapshots]
    E --> F[Schema normalization]
    F --> G[Source ID deduplication]
    G --> H[Requirement extraction]
    H --> I[Rule-based evaluators]

    I --> J{Decision}
    J --> K[APPLY]
    J --> L[REVIEW]
    J --> M[SKIP]

    I --> N[Evaluated JSON]
    N --> O[Run metadata]
```
## Engineering decisions

- Source failures are not treated as successful empty results.
- Missing evidence is kept separate from explicit incompatibility.
- Raw and evaluated snapshots are persisted for traceability.
- Requirement extraction is deterministic and explainable.
- External API calls are excluded from the regression test suite.

Outputs are written under `data/` and are intentionally excluded from Git.

## Local setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --frozen
uv run python -m job_market_intelligence
```

The installed command is equivalent:

```bash
uv run job-market-intelligence
```

Run the regression suite without external API calls:

```bash
uv run python -m unittest discover -s tests -v
```

## Airflow and Docker

The DAG runs at 09:00 Europe/Copenhagen time on weekdays. Build and start the
standalone Airflow image with:

```bash
docker build -t job-radar .
docker run --rm -p 8080:8080 \
  -v "$PWD/data:/app/data" \
  job-radar
```

The data volume is required. Without it, raw files, evaluated results, and run
metadata disappear when the container is removed.

## Known limitations

- Candidate skills and target geography are still hard-coded.
- Deduplication is exact by source ID; the same vacancy syndicated by two
  providers can remain twice.
- External Jobindex application pages can block scraping, leaving a short or
  empty description that must remain `REVIEW`.
- Requirement extraction is deterministic and conservative, not a general NLP
  model. New ATS heading variants need regression fixtures before parser changes.
- The pipeline creates full snapshots; it does not yet track new, changed,
  expired, or already-reviewed vacancies across runs.


## Example output

A synthetic evaluated-job example is available in
[`examples/sample_evaluated_jobs.json`](examples/sample_evaluated_jobs.json).

The example contains no real employer, vacancy, applicant, or job-description
data. Runtime data under `data/` is excluded from Git.