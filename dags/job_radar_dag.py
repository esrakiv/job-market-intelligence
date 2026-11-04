from datetime import timedelta

import pendulum

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator


with DAG(
    dag_id="job_radar_pipeline",
    schedule="0 9 * * 1-5",
    start_date=pendulum.datetime(
        2026,
        9,
        1,
        tz="Europe/Copenhagen",
    ),
    catchup=False,
    max_active_runs=1,
) as dag:
    run_job_radar = BashOperator(
        task_id="run_job_radar",
        bash_command="cd /app && uv run --frozen python -m job_market_intelligence",
        env={"JOB_RADAR_RUN_ID": "{{ run_id }}"},
        append_env=True,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )

