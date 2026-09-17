import time
from urllib import response
from pathlib import Path
from datetime import datetime
import json  
import requests 
import logging
logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]

def save_raw_jobs(data, title, industry):
    # Get the current date and time
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Create a filename with the timestamp
    filename = f"raw_jobs_{title}_{industry}_{timestamp}.json"
    #What if there is no folder called data/raw? I will create it if it does not exist.
    Path('data/raw').mkdir(parents=True, exist_ok=True)
    # Define the path to save the file
    file_path = Path('data/raw') / filename
 
    # Save the data to a JSON file
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)
    return str(file_path)

def process_jobs(raw_batches):
    jobs_by_id = {}

    for batch in raw_batches:  
        title = batch['title']
        ind = batch['industry']
        for job in batch["jobs"]:
            job_id = job["id"]
            job["classification"] = classify_job_title(job["jobTitle"]) 
            if job_id not in jobs_by_id:  # jobs_by_id is a dictionary where the key is job_id and the value is the job dict
                jobs_by_id[job_id] = {
                    **job,
                    "matchedSourcestitle": [title],
                    "matchedSourcesindustry": [ind] 
                }
            else:
                if title not in jobs_by_id[job_id]["matchedSourcestitle"]:
                    jobs_by_id[job_id]["matchedSourcestitle"].append(title)
                if ind not in jobs_by_id[job_id]["matchedSourcesindustry"]:    
                    jobs_by_id[job_id]["matchedSourcesindustry"].append(ind) 
                    
    all_jobs = list(jobs_by_id.values()) 
    return all_jobs

def save_processed_jobs(data, title):
    # Get the current date and time
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Create a filename with the timestamp
    filename = f"processed_jobs_{title}_{timestamp}.json"
    #What if there is no folder called data/processed? I will create it if it does not exist.
    Path('data/processed').mkdir(parents=True, exist_ok=True)
    # Define the path to save the file
    file_path = Path('data/processed') / filename
# Save the data to a JSON file
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)
    return str(file_path)

def save_curated_jobs(data, title):
    # Get the current date and time
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Create a filename with the timestamp
    filename = f"curated_jobs_{title}_{timestamp}.json"
    #What if there is no folder called data/curated? I will create it if it does not exist.
    Path('data/curated').mkdir(parents=True, exist_ok=True)
    # Define the path to save the file
    file_path = Path('data/curated') / filename
    # Save the data to a JSON file
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)    
    return str(file_path)

def save_run_metadata(
    total_fetched,
    unique_jobs,
    curated_jobs,
    actionable_jobs,
    run_id
):
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    
    metadata = {
        "run_timestamp": timestamp,
        "total_fetched": total_fetched,
        "unique_jobs": unique_jobs,
        "curated_jobs": curated_jobs,
        "actionable_jobs": actionable_jobs,
        "airflow_run_id": run_id
    }
    
    Path("data/run_metadata").mkdir(parents=True, exist_ok=True)

    file_path = Path("data/run_metadata") / f"run_{timestamp}.json"

    with open(file_path, "w") as f:
        json.dump(metadata, f, indent=4)
 

def validate_response_schema(data):
    if not isinstance(data, dict):
        raise ValueError("API response must be a dictionary")

    if "jobs" not in data:
        raise ValueError("API response is missing 'jobs' key")

    if not isinstance(data["jobs"], list):
        raise ValueError("'jobs' must be a list")

    return True

def ingest_job():
    titles = [
        "data engineer",
        "analytics engineer", 
        ]
    industry = ["engineering", "data-science"]
    raw_files = []
    total_fetched_before_dedup = 0
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
 
    for title in titles:
        for ind in industry:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=50&geo=europe&tag={title}&industry={ind}"
            data = fetch_jobs(url)
             
            raw_file_path = save_raw_jobs(data, title, ind)

            
            fetched_jobs = data.get("jobs", []) # data type is list, inside there are dictionaries 
            total_fetched_before_dedup += len(fetched_jobs) 
            raw_files.append({'title':title, 'industry':ind, 'path':raw_file_path})

    return raw_files, total_fetched_before_dedup


def fetch_jobs(url):

    #how to retry 3 times if the request fails due to a network error or timeout, with a delay of 2 seconds between retries.
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = response.json()  
            validate_response_schema(data)
            return data 
        # request exception codes 429, 500  
        except requests.HTTPError as e:
            status_code = e.response.status_code

            if status_code not in RETRYABLE_STATUS_CODES:
                raise
            logger.warning(
                "Attempt %s failed with status %s",
                attempt + 1,
                status_code
            )
            if attempt < 2:
                time.sleep(2)
            else:
                raise
            
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.warning(
                "Attempt %s failed due to network error: %s",
                attempt + 1,
                e
            )
            if attempt < 2:
                time.sleep(2)
            else:
                raise e
 

def classify_job_title(job_title):
    job_title_lower = job_title.lower()
    adjacent_keywords = [
    "data platform",
    "data infrastructure",
    "data architect",
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "ai engineer",
    "etl developer",
    "data warehouse engineer",
    ]
    core_keywords = [
    "data engineer",
    "analytics engineer",
    "business intelligence engineer",
    "business intelligence analyst",
    "BI engineer",
    "BI analyst",
    ]
    for keyword in core_keywords + adjacent_keywords:
        if any(keyword in job_title_lower for keyword in core_keywords):
            return "CORE" 
        elif any(keyword in job_title_lower for keyword in adjacent_keywords):
            return "ADJACENT"
        else:
            return "NON_TARGET" 

def create_curated_jobs(processed_jobs):
    curated_jobs = []
    count_non_target =0 
    for job in processed_jobs:
        if job["classification"] in ["CORE", "ADJACENT"]: 
            curated_jobs.append(job)
        else:
            count_non_target +=1


    return curated_jobs, count_non_target

def is_actionable_for_CV(job):
    title = job.get("jobTitle", "").lower()
    level = job.get("jobLevel", "")
    geo = job.get("jobGeo", "")
    job_types = job.get("jobType", [])


    return True if all([
        level in ["Senior", "mid-level", "Midweight"], 
        any(location in geo for location in ["Denmark", "Europe", "EMEA", "Anywhere"]),
        any(jt in ["Full-Time", "Permanent"] for jt in job_types),
        any(keyword in title for keyword in ["data engineer", "analytics engineer"])
    ]
    ) else False

def extract_skills(job):
    SKILL_WEIGHTS = {
    "sql": 5,
    "dbt": 5,
    "snowflake": 5,
    "data modeling": 5,

    "etl": 4,
    "elt": 4,
    "airflow": 3,
    "python": 3,

    "azure": 2,
    "aws": 2,
    "gcp": 2,
    "databricks": 2,
    "spark": 2,

    "kafka": 1,
    "terraform": 1,
    "kubernetes": 1,
    }
    text = job.get("jobDescription", "").lower() 
    found_skills = []

    for skill, weight in SKILL_WEIGHTS.items():
        if skill in text:
            found_skills.append((skill, weight))

    return found_skills

def calculate_fit_level(job):
    skills = extract_skills(job) 
     

    total_weight = sum(weight for _, weight in skills)

    if total_weight >= 20:
        return "High", total_weight, skills
    elif total_weight >= 10:
        return "Medium", total_weight, skills
    else:
        return "Low", total_weight, skills

def calculate_seniority_fit(job):
    title = job.get("jobTitle", "").lower()
    level = job.get("jobLevel", "").lower()

    if "principal" in title:
        return "STRETCH"

    if "staff" in title:
        return "MEDIUM"

    if "lead" in title:
        return "MEDIUM"

    if level in ["senior", "midweight", "mid-level"]:
        return "HIGH"

    if level in ["junior", "intern", "entry-level"]:
        return "LOW"

    return "UNKNOWN"

def calculate_overall_fit(technical_fit, seniority_fit):
    if technical_fit == "High" and seniority_fit == "HIGH":
        return "HIGH"

    if technical_fit in ["High", "Medium"] and seniority_fit in ["HIGH", "MEDIUM"]:
        return "MEDIUM"

    return "LOW"

def transform_jobs(raw_files):
    raw_batches = []

    for raw_file in raw_files:
        with open(raw_file["path"]) as f:
            data = json.load(f)
        raw_batches.append({
            "title": raw_file["title"],
            "industry": raw_file["industry"],
            "jobs": data.get("jobs", []),
        })
    all_jobs = process_jobs(raw_batches)

    save_processed_jobs(
        all_jobs,
        "all_titles",
    )

    curated_jobs, non_target_count = create_curated_jobs(all_jobs)

    save_curated_jobs(
        curated_jobs,
        "curated_jobs",
    )
    actionable_count = 0
    actionable_jobs = [] 
    for job in curated_jobs:
        if is_actionable_for_CV(job):
            actionable_count += 1
            actionable_jobs.append(job) 

    

    return all_jobs, curated_jobs, non_target_count,actionable_jobs,actionable_count