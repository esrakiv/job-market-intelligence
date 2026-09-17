from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from datetime import datetime, timedelta
import json
import logging
import pendulum

from job_market_intelligence.job_api_client import ingest_job, transform_jobs

logger = logging.getLogger(__name__)


# @dag(
#     dag_id="job_radar_pipeline",
#     schedule=None,
#     start_date=datetime(2026, 9, 1),
#     catchup=False,
# )
# def job_radar_pipeline():
    
#     @task
#     def ingest():
#         logger.info("INGEST STARTED")
#         return ingest_job()
        
#     @task
#     def transforming(ingest_result):
#         logger.info("PROCESS STARTED")
#         raw_files, total_fetched = ingest_result
         
#         transform_result =  transform_jobs(raw_files)
#         return {
#             "total_fetched": total_fetched,
#             "transform_result": transform_result,
#         }

#     ingest_result = ingest()
#     transforming(ingest_result)
    #job_radar_pipeline()



with DAG(
    dag_id="job_radar_pipeline",
    schedule="0 9 * * 1-5" ,
    start_date=pendulum.datetime(
        2026, 9, 1, tz="Europe/Copenhagen",),
    catchup=False,
) as dag:
    run_job_radar = BashOperator(
        task_id="run_job_radar",
        bash_command="""
        cd /app &&
        uv run python -m job_market_intelligence
        """,
        env={
        "JOB_RADAR_RUN_ID": "{{ run_id }}"
        },
        append_env=True,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )  

