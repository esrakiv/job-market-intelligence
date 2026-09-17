import logging
import os

from job_market_intelligence.job_api_client import *


def main() -> None:
    run_id = os.getenv("JOB_RADAR_RUN_ID")
    raw_batches, total_fetched_before_dedup = ingest_job()
    
    all_jobs, curated_jobs, non_target_count,actionable_jobs, actionable_count = transform_jobs(raw_batches)
    if run_id is None:
        run_id = f"manual__{datetime.now().isoformat()}" 
    logger.info("Run ID: %s", run_id)
    curated_jobs_count = len(curated_jobs)
    unique_jobs_count = len(all_jobs) 
     

    save_run_metadata(total_fetched_before_dedup, unique_jobs_count, curated_jobs_count, actionable_count, run_id)

    logger.info("Job Radar run completed")
    logger.info(f"Fetched jobs: {total_fetched_before_dedup}")
    logger.info(f"Unique jobs: {unique_jobs_count}")
    logger.info(f"Curated jobs: {curated_jobs_count}")
    logger.info(f"Non-target jobs: {non_target_count}")
    logger.info(f"Actionable jobs: {actionable_count}")
    logger.info("\nTop actionable roles:")
    for job in actionable_jobs:
        fit_level = calculate_overall_fit(
            calculate_fit_level(job)[0],
            calculate_seniority_fit(job)
         )

        print(
            f"- {job['jobTitle']} — "
            
            f"{job['companyName']} — "
            f"{fit_level}"
        )


if __name__ == "__main__":
    main()  