import logging
import os
from collections import Counter

from job_market_intelligence.job_api_client import (
    ingest_job,
    transform_jobs,
    save_run_metadata,
)

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    run_id = os.getenv("JOB_RADAR_RUN_ID", "manual")

    logger.info("Starting Job Radar pipeline")
    logger.info("Run ID: %s", run_id)

    # 1. INGEST
    raw_files, total_fetched = ingest_job()

    logger.info("Fetched %s jobs before deduplication", total_fetched)

    # 2. TRANSFORM + EVALUATE
    (
        all_jobs,
        evaluated_jobs,
        decision_buckets,
    ) = transform_jobs(raw_files)

    unique_jobs = len(all_jobs)
    source_counts = dict(
        Counter(job.get("source", "unknown") for job in all_jobs)
    )

    apply_jobs = decision_buckets["APPLY"]
    review_jobs = decision_buckets["REVIEW"]
    skip_jobs = decision_buckets["SKIP"]
    direct_target_jobs = [
        job
        for job in evaluated_jobs
        if job["evaluation"]["role"]["role_fit"] == "HIGH"
    ]

    # 3. METADATA
    save_run_metadata(
        total_fetched=total_fetched,
        unique_jobs=unique_jobs,
        apply_jobs=len(apply_jobs),
        review_jobs=len(review_jobs),
        skip_jobs=len(skip_jobs),
        run_id=run_id,
        source_counts=source_counts,
    )

    print("\n=== JOBINDEX JOBS ===")

    for job in evaluated_jobs:
        if job.get("source") == "jobindex":
            reasons = "; ".join(job["decision_reasons"])
            print(
                f"{job['jobTitle']} | "
                f"{job['companyName']} | "
                f"{job.get('jobGeo', 'Unknown')} | "
                f"{job['decision']} | "
                f"{reasons}"
            )
    # 4. SUMMARY
    logger.info(
        "Pipeline completed | fetched=%s unique=%s direct_targets=%s "
        "apply=%s review=%s skip=%s",
        total_fetched,
        unique_jobs,
        len(direct_target_jobs),
        len(apply_jobs),
        len(review_jobs),
        len(skip_jobs),
    )

    print("\n=== JOB RADAR SUMMARY ===")
    print(f"Fetched: {total_fetched}")
    print(f"Unique:  {unique_jobs}")
    print(f"Direct target roles: {len(direct_target_jobs)}")
    print(f"APPLY:   {len(apply_jobs)}")
    print(f"REVIEW:  {len(review_jobs)}")
    print(f"SKIP:    {len(skip_jobs)}")

    if direct_target_jobs:
        print("\n=== DIRECT TARGET ROLES ===")

        for job in direct_target_jobs:
            reasons = "; ".join(job["decision_reasons"])
            print(
                f"- {job['jobTitle']} | "
                f"{job['companyName']} | "
                f"{job.get('jobGeo', 'Unknown')} | "
                f"{job['decision']} | "
                f"{reasons}"
            )

    if apply_jobs:
        print("\n=== APPLY ===")

        for job in apply_jobs:
            print(
                f"- {job['jobTitle']} | "
                f"{job['companyName']} | "
                f"{job.get('jobGeo', 'Unknown')}"
            )


if __name__ == "__main__":
    main()
