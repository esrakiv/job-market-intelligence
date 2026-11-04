import json
import logging
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException


DetectorFactory.seed = 0
logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
JOBICY_JOBS_URL = "https://jobicy.com/api/v2/remote-jobs"
ARBEITNOW_JOBS_URL = "https://www.arbeitnow.com/api/job-board-api"
ARBEITNOW_MAX_PAGES = 10
ARBEITNOW_PAGE_DELAY_SECONDS = 1
JOBINDEX_SEARCH_URL = "https://www.jobindex.dk/jobsoegning"
JOBINDEX_DETAIL_URL = "https://www.jobindex.dk/jobannonce"

JOBINDEX_QUERIES = [
    '"data engineer"',
    '"senior data engineer"',
    '"analytics engineer"',
    '"data architect"',
    '"data platform engineer"',
    '"data warehouse engineer"',
]
JOBINDEX_MAX_PAGES = 5
JOBINDEX_JOB_AGE_DAYS = 30
JOBINDEX_REQUEST_DELAY_SECONDS = 0.5
JOBINDEX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,da;q=0.8",
}
ARBEITNOW_TARGET_TITLE_KEYWORDS = {
    "data engineer",
    "analytics engineer",
    "data platform",
    "data infrastructure",
    "data architect",
    "data warehouse engineer",
    "business intelligence engineer",
    "bi engineer",
    "etl developer",
}
REMOTE_LOCATION_PASS = {
    "anywhere",
    "work from anywhere",
    "worldwide",
    "global",
    "denmark",
    "europe",
    "european union",
    "eu",
    "eea",
}
REMOTE_LOCATION_REVIEW = {
    "remote",
    "emea",
}
REMOTE_RESTRICTED_COUNTRIES = {
    "austria",
    "belgium",
    "bulgaria",
    "czechia",
    "finland",
    "france",
    "germany",
    "hungary",
    "ireland",
    "italy",
    "netherlands",
    "norway",
    "poland",
    "portugal",
    "spain",
    "sweden",
    "switzerland",
    "uk",
    "united kingdom",
    "ukraine",
}

SKILL_ALIASES = {
    "sql": ["sql", "t-sql", "sql server"],
    "python": ["python"],
    "bash": ["bash", "shell scripting"],
    "dbt": ["dbt"],
    "snowflake": ["snowflake"],
    "airflow": ["airflow"],
    "airbyte": ["airbyte"],
    "spark": ["spark", "pyspark"],
    "databricks": ["databricks"],
    "redshift": ["redshift", "amazon redshift"],
    "azure": ["azure"],
    "aws": ["aws", "amazon web services"],
    "gcp": ["gcp", "google cloud"],
    "bigquery": ["bigquery"],
    "clickhouse": ["clickhouse"],
    "kafka": ["kafka"],
    "terraform": ["terraform"],
    "kubernetes": ["kubernetes", "k8s"],
    "javascript": ["javascript"],
    # Do not use plain "gtm" here. In business job ads it often means
    # go-to-market rather than Google Tag Manager.
    "google_tag_manager": ["google tag manager"],
    "conversion_tracking": [
        "conversion setup",
        "conversion tracking",
        "pixels",
        "pixel tracking",
    ],
    "google_ads": ["google ads"],
    "meta_ads": ["meta ads", "facebook ads"],
    "bing_ads": ["bing ads"],
    "data_modeling": [
        "data modeling",
        "data modelling",
        "dimensional modeling",
        "dimensional modelling",
    ],
    "data_quality": ["data quality", "data validation"],
    "edi": ["edi", "edifact", "ansi x12", "peppol", "as2", "oftp2"],
    "microsoft_fabric": [
        "microsoft fabric",
        "fabric lakehouse",
    ],
    "power_bi": [
        "power bi",
        "powerbi",
    ],
    "azure_data_factory": [
        "azure data factory",
    ],
    "cicd": [
        "ci/cd",
        "ci-cd",
        "continuous integration",
        "continuous delivery",
    ],
    "etl_elt": [
        "etl",
        "elt",
        "etl/elt",
        "elt/etl",
    ],
    "semantic_layer": [
        "semantic layer",
        "semantic layers",
        "semantic model",
        "semantic models",
    ],
}

MIN_REQUIREMENT_DESCRIPTION_LENGTH = 500

CANDIDATE_SKILLS = {
    "sql",
    "dbt",
    "snowflake",
    "airflow",
    "python",
    "data_modeling",
    "data_quality",
    "azure_data_factory",
    "cicd",
    "etl_elt",
}
CANDIDATE_GROWTH_SKILLS = {
    "databricks",
    "spark",
    "terraform",
    "kubernetes",
}

REQUIRED_HEADINGS = {
    "requirements",
    "qualifications",
    "what we are looking for",
    "what we're looking for",
    "what we look for",
    "must have",
    "what you bring",
    "important to have",

    # Arbeitnow / common job-posting variants
    "your profile",
    "your qualifications",
    "about you",
    "who you are",
    "what you'll bring",
    "what you’ll bring",
    "skills and qualifications",
    "experience and qualifications",
    "who we're looking for",
    "who we are looking for",
    "we are looking for",

    # Common Danish headings on Jobindex and employer career pages.
    "kvalifikationer",
    "dine kvalifikationer",
    "faglige kvalifikationer",
    "vi forestiller os, at du",
    "vi søger dig, der",
    "om dig",
    "fagligt",
}
PREFERRED_HEADINGS = {
    "nice to have",
    "nice-to-have",
    "preferred",
    "bonus",
    "additional skills",
    "you will be preferred if",
    "advantage",
    "plus",
}
SECONDARY_MARKERS = {
    "basic understanding",
    "familiarity",
    "exposure to",
    "working knowledge",
}
STOP_HEADINGS = {
    "what you'll do",
    "what you’ll do",
    "responsibilities",
    "your role",
    "what we offer",
    "total rewards",
    "benefits",
    "location",
    "remote-first",
    "job description",
    "working environment",
    "application",
    "application & security clearance",
    "om rollen",
    "dine hovedopgaver",
    "vi tilbyder",
    "om os",

}
REQUIRED_HEADINGS.update({
    "what you'll need",                       # Insify
    "what you would bring",                   # Mews
    "what really gets us excited about you",  # Contentstack
    "we imagine you're someone who",          # OOONO
    "your technical toolbox",                 # Daka
    "what will make you successful",          # Arla
    "what will help you succeed",             # Schneider Electric
    "hvem er du",                             # Middelfart
})

PREFERRED_HEADINGS.update({
    "even better if you've worked with",      # OOONO
})

STOP_HEADINGS.update({
    "what do we offer",
    "our stack",
    "the practical stuff",
    "personal competences",
    "diversity & inclusion",
    "keep your personal data safe",
})

STOP_HEADING_PREFIXES = {
    "why join",
    "how is it working at",
    "pay transparency",
    "hvorfor",
}

INLINE_SECTION_HEADINGS = (
    "what we are looking for",
    "what we're looking for",
    "what you'll need",
    "what you would bring",
    "what really gets us excited about you",
    "we imagine you're someone who",
    "your technical toolbox",
    "what will make you successful",
    "hvem er du",
    "even better if you've worked with",
    "nice to have",
    "personal competences",
    "what we offer",
    "what do we offer",
    "diversity & inclusion",
    "keep your personal data safe",
)

PREFERRED_LINE_MARKERS = (
    "nice to have",
    "nice-to-have",
    "would be a plus",
    "is a plus",
    "an advantage",
    "preferred but not required",
)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


def validate_response_schema(data):
    if not isinstance(data, dict):
        raise ValueError("API response must be a dictionary")
    if "jobs" not in data:
        raise ValueError("API response is missing 'jobs' key")
    if not isinstance(data["jobs"], list):
        raise ValueError("'jobs' must be a list")
    return True


def fetch_jobs(url, params=None):
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            validate_response_schema(data)
            return data
        except requests.HTTPError as error:
            status_code = error.response.status_code
            if status_code not in RETRYABLE_STATUS_CODES:
                raise
            logger.warning(
                "Attempt %s failed with status %s",
                attempt + 1,
                status_code,
            )
        except (requests.Timeout, requests.ConnectionError) as error:
            logger.warning(
                "Attempt %s failed due to network error: %s",
                attempt + 1,
                error,
            )

        if attempt < 2:
            time.sleep(2)

    raise RuntimeError("Job API request failed after three attempts")


def fetch_all_job_pages(params):
    all_jobs = []
    first_page = None
    cursor = None
    seen_cursors = set()
    pages_fetched = 0

    while True:
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor

        page = fetch_jobs(JOBICY_JOBS_URL, params=page_params)
        if first_page is None:
            first_page = dict(page)

        page_jobs = page.get("jobs", [])
        all_jobs.extend(page_jobs)
        pages_fetched += 1

        logger.info(
            "Fetched Jobicy page %s | tag=%s industry=%s jobs=%s has_more=%s",
            pages_fetched,
            params["tag"],
            params["industry"],
            len(page_jobs),
            page.get("hasMore", False),
        )

        next_cursor = page.get("nextCursor")
        if not next_cursor:
            break
        if next_cursor in seen_cursors:
            raise RuntimeError("Jobicy returned a repeated pagination cursor")

        seen_cursors.add(next_cursor)
        cursor = next_cursor

    combined_response = first_page or {"jobs": []}
    combined_response.update(
        {
            "jobs": all_jobs,
            "jobCount": len(all_jobs),
            "nextCursor": None,
            "hasMore": False,
            "pagesFetched": pages_fetched,
        }
    )
    return combined_response


def save_raw_jobs(data, title, industry):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_directory = Path("data/raw")
    output_directory.mkdir(parents=True, exist_ok=True)
    file_path = output_directory / f"raw_jobs_{title}_{industry}_{timestamp}.json"

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    return str(file_path)


def normalize_jobicy_job(job):
    source_id = job.get("id")

    if source_id is None:
        return None

    return {
        **job,
        "id": f"jobicy:{source_id}",
        "source": "jobicy",
        "sourceJobId": source_id,
    }


def ingest_jobicy_jobs():
    titles = ["data engineer", "analytics engineer"]
    industries = ["engineering", "data-science"]
    raw_files = []
    total_fetched = 0

    for title in titles:
        for industry in industries:
            params = {
                "count": 200,
                "geo": "europe",
                "tag": title,
                "industry": industry,
            }
            data = fetch_all_job_pages(params)
            normalized_jobs = [
                normalized_job
                for job in data.get("jobs", [])
                if (normalized_job := normalize_jobicy_job(job)) is not None
            ]
            data = {
                **data,
                "source": "jobicy",
                "jobs": normalized_jobs,
                "jobCount": len(normalized_jobs),
            }
            raw_file_path = save_raw_jobs(data, title, industry)
            total_fetched += len(normalized_jobs)
            raw_files.append(
                {
                    "title": title,
                    "industry": industry,
                    "path": raw_file_path,
                }
            )

    return raw_files, total_fetched

def fetch_arbeitnow_page(page_number):
    for attempt in range(3):
        try:
            response = requests.get(
                ARBEITNOW_JOBS_URL,
                params={"page": page_number},
                timeout=20,
            )
            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):
                raise ValueError("Arbeitnow response must be a dictionary")

            if not isinstance(data.get("data"), list):
                raise ValueError("Arbeitnow response is missing data list")

            return data

        except requests.HTTPError as error:
            status_code = error.response.status_code

            if status_code not in RETRYABLE_STATUS_CODES:
                raise

            logger.warning(
                "Arbeitnow page %s attempt %s failed with status %s",
                page_number,
                attempt + 1,
                status_code,
            )

        except (requests.Timeout, requests.ConnectionError) as error:
            logger.warning(
                "Arbeitnow page %s attempt %s failed: %s",
                page_number,
                attempt + 1,
                error,
            )

        if attempt < 2:
            time.sleep(2)

    raise RuntimeError(
        f"Arbeitnow page {page_number} failed after three attempts"
    )


def fetch_all_arbeitnow_pages():
    jobs_by_slug = {}

    for page_number in range(1, ARBEITNOW_MAX_PAGES + 1):
        page = fetch_arbeitnow_page(page_number)
        page_jobs = page.get("data", [])

        for job in page_jobs:
            source_id = job.get("slug") or job.get("url")

            if source_id:
                jobs_by_slug[source_id] = job

        has_more = bool(page.get("links", {}).get("next"))

        logger.info(
            "Fetched Arbeitnow page %s | jobs=%s has_more=%s",
            page_number,
            len(page_jobs),
            has_more,
        )

        if not has_more:
            break

        if page_number < ARBEITNOW_MAX_PAGES:
            time.sleep(ARBEITNOW_PAGE_DELAY_SECONDS)

    return list(jobs_by_slug.values())


def infer_arbeitnow_job_level(title):
    title_lower = title.lower()

    if "principal" in title_lower:
        return "Principal"

    if "staff" in title_lower:
        return "Staff"

    if "senior" in title_lower:
        return "Senior"

    if any(
        level in title_lower
        for level in ["junior", "entry", "intern"]
    ):
        return "Junior"

    return ""


def normalize_arbeitnow_job(job):
    description = job.get("description", "") or ""

    description_text = BeautifulSoup(
        description,
        "html.parser",
    ).get_text(" ", strip=True)

    excerpt = " ".join(description_text.split()[:55])

    source_id = job.get("slug") or job.get("url")
    created_at = job.get("created_at")
    publication_date = None

    if isinstance(created_at, (int, float)):
        publication_date = datetime.fromtimestamp(
            created_at,
            tz=timezone.utc,
        ).isoformat()

    location = job.get("location") or (
        "Remote" if job.get("remote") else "Unknown"
    )

    return {
        "id": f"arbeitnow:{source_id}",
        "source": "arbeitnow",
        "sourceJobId": source_id,
        "url": job.get("url", ""),
        "jobTitle": job.get("title", ""),
        "companyName": job.get("company_name", ""),
        "companyLogo": None,
        "jobIndustry": job.get("tags") or [],
        "jobType": job.get("job_types") or [],
        "jobGeo": location,
        "jobLevel": infer_arbeitnow_job_level(
            job.get("title", "")
        ),
        "jobExcerpt": excerpt,
        "jobDescription": description,
        "pubDate": publication_date,
        "remote": bool(job.get("remote")),
    }


def ingest_arbeitnow_jobs():
    downloaded_jobs = fetch_all_arbeitnow_pages()
    normalized_jobs = []

    for job in downloaded_jobs:
        title = job.get("title", "").lower()

        is_target_role = any(
            keyword in title
            for keyword in ARBEITNOW_TARGET_TITLE_KEYWORDS
        )

        if not is_target_role:
            continue

        normalized_jobs.append(
            normalize_arbeitnow_job(job)
        )

    logger.info(
        "Arbeitnow downloaded=%s target_roles=%s",
        len(downloaded_jobs),
        len(normalized_jobs),
    )

    data = {
        "source": "arbeitnow",
        "downloadedJobCount": len(downloaded_jobs),
        "jobCount": len(normalized_jobs),
        "jobs": normalized_jobs,
    }

    raw_file_path = save_raw_jobs(
        data,
        "target roles",
        "arbeitnow",
    )

    raw_file = {
        "title": "target roles",
        "industry": "arbeitnow",
        "path": raw_file_path,
    }

    return raw_file, len(normalized_jobs)

def ingest_job():
    jobicy_raw_files, jobicy_count = ingest_jobicy_jobs()

    arbeitnow_raw_file, arbeitnow_count = (
        ingest_arbeitnow_jobs()
    )

    jobindex_raw_file, jobindex_count = (
        ingest_jobindex_jobs()
    )

    raw_files = [
        *jobicy_raw_files,
        arbeitnow_raw_file,
        jobindex_raw_file,
    ]

    total_fetched = (
        jobicy_count
        + arbeitnow_count
        + jobindex_count
    )

    return raw_files, total_fetched

# ---------------------------------------------------------------------------
# Deduplication and requirement extraction
# ---------------------------------------------------------------------------


def process_jobs(raw_batches):
    jobs_by_id = {}

    for batch in raw_batches:
        title = batch["title"]
        industry = batch["industry"]

        for job in batch["jobs"]:
            job_id = job["id"]

            if job_id not in jobs_by_id:
                jobs_by_id[job_id] = {
                    **job,
                    "matched_query_titles": [title],
                    "matched_query_industries": [industry],
                }
                continue

            stored_job = jobs_by_id[job_id]
            if title not in stored_job["matched_query_titles"]:
                stored_job["matched_query_titles"].append(title)
            if industry not in stored_job["matched_query_industries"]:
                stored_job["matched_query_industries"].append(industry)

    return list(jobs_by_id.values())


def clean_job_text(job):
    text = " ".join(
        [
            job.get("jobTitle", ""),
            job.get("jobExcerpt", ""),
            job.get("jobDescription", ""),
        ]
    )
    text = unescape(text).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def repair_mojibake(value):
    """Repair the common UTF-8-as-Latin-1/Windows-1252 corruption."""
    if not isinstance(value, str) or not value:
        return value

    repaired = value
    markers = ("Ã", "Â", "â", "ð", "�")

    for _ in range(2):
        if not any(marker in repaired for marker in markers):
            break

        candidates = []

        for encoding in ("latin-1", "cp1252"):
            try:
                candidate = repaired.encode(encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue

            candidates.append(candidate)

        if not candidates:
            break

        best = min(
            candidates,
            key=lambda text: sum(text.count(marker) for marker in markers),
        )

        old_score = sum(repaired.count(marker) for marker in markers)
        new_score = sum(best.count(marker) for marker in markers)

        if new_score >= old_score:
            break

        repaired = best

    return repaired


def extract_skills_from_text(text):
    text = text.lower()
    found_skills = []

    for skill, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
            if re.search(pattern, text):
                found_skills.append(skill)
                break

    return found_skills

def extract_jobindex_stash(html):
    marker = "var Stash = "
    marker_position = html.find(marker)

    if marker_position == -1:
        raise ValueError("Jobindex Stash data not found")

    start = html.find("{", marker_position + len(marker))

    if start == -1:
        raise ValueError("Jobindex Stash JSON start not found")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(html)):
        char = html[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

            if depth == 0:
                return json.loads(html[start:index + 1])

    raise ValueError("Jobindex Stash JSON is incomplete")


def fetch_jobindex_search_page(query, page_number):
    params = {
        "q": query,
        "jobage": JOBINDEX_JOB_AGE_DAYS,
        "sort": "score",
        "page": page_number,
    }

    last_error = None

    for attempt in range(3):
        try:
            response = requests.get(
                JOBINDEX_SEARCH_URL,
                params=params,
                headers=JOBINDEX_HEADERS,
                timeout=(10, 45),
                allow_redirects=True,
            )
            logger.info(
                "Jobindex HTTP | query=%s page=%s status=%s url=%s",
                query,
                page_number,
                response.status_code,
                response.url,
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            response.encoding = "utf-8"
            stash = extract_jobindex_stash(response.text)
            search_response = (
                stash
                .get("jobsearch/result_app/list", {})
                .get("storeData", {})
                .get("searchResponse", {})
            )

            results = search_response.get("results", [])

            logger.info(
                "Jobindex raw search | query=%s page=%s results=%s first_ids=%s",
                query,
                page_number,
                len(results),
                [
                    {
                        "tid": job.get("tid"),
                        "headline": job.get("headline"),
                    }
                    for job in results[:5]
                ],
            )

            return results

        except (
            requests.Timeout,
            requests.ConnectionError,
        ) as error:
            last_error = error
            logger.warning(
                "Jobindex search failed | "
                "query=%s page=%s attempt=%s error=%s",
                query,
                page_number,
                attempt + 1,
                error,
            )

        except requests.HTTPError as error:
            last_error = error
            logger.warning(
                "Jobindex HTTP error | "
                "query=%s page=%s attempt=%s status=%s",
                query,
                page_number,
                attempt + 1,
                error.response.status_code,
            )

        if attempt < 2:
            time.sleep(2 * (attempt + 1))

    raise RuntimeError(
        "Jobindex search unavailable after retries "
        f"for query={query!r} page={page_number}"
    ) from last_error


def _extract_jobposting_jsonld(soup):
    """Return structured JobPosting data embedded by external career pages."""

    def iter_nodes(value):
        if isinstance(value, list):
            for item in value:
                yield from iter_nodes(item)
            return

        if not isinstance(value, dict):
            return

        node_type = value.get("@type")
        node_types = node_type if isinstance(node_type, list) else [node_type]

        if "JobPosting" in node_types:
            yield value

        yield from iter_nodes(value.get("@graph"))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_json = script.string or script.get_text()

        if not raw_json.strip():
            continue

        try:
            payload = json.loads(raw_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

        for node in iter_nodes(payload):
            description = node.get("description")

            if isinstance(description, str) and description.strip():
                return description

    return ""


def fetch_jobindex_detail(job_id):
    url = f"{JOBINDEX_DETAIL_URL}/{job_id}"

    response = requests.get(
        url,
        headers=JOBINDEX_HEADERS,
        timeout=(10, 45),
        allow_redirects=False,
    )

    is_external = False

    if response.status_code in {301, 302, 303, 307, 308}:
        redirect_location = response.headers.get("Location")

        if not redirect_location:
            return {
                "description": "",
                "location": None,
                "url": url,
                "external": False,
            }

        external_url = urljoin(response.url, redirect_location)
        is_external = True

        logger.info(
            "Jobindex external job | id=%s url=%s",
            job_id,
            external_url,
        )

        try:
            external_response = requests.get(
                external_url,
                headers=JOBINDEX_HEADERS,
                timeout=(10, 45),
                allow_redirects=True,
            )
            external_response.raise_for_status()
            response = external_response
        except requests.RequestException as error:
            logger.info(
                "External detail unavailable; keeping redirect URL | "
                "id=%s url=%s error=%s",
                job_id,
                external_url,
                error,
            )
            return {
                "description": "",
                "location": None,
                "url": external_url,
                "external": True,
            }

    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"

    soup = BeautifulSoup(response.text, "html.parser")

    description_element = (
        soup.select_one(".jd-description")
        or soup.select_one('[itemprop="description"]')
        or soup.select_one(".job-description")
        or soup.select_one(".jobtext-jobad__main")
        or soup.select_one(".jobtext-jobad")
        or soup.select_one(".job-content.col-lg-8 .job-content")
        or soup.select_one(".white-bg > .job-content")
        or soup.select_one("article")
        or soup.select_one("main")
    )

    if description_element:
        # Keep HTML structure. Requirement extraction depends on headings and
        # list items; get_text(" ") destroyed that information.
        description = str(description_element)
    else:
        description = _extract_jobposting_jsonld(soup)

        if not description:
            meta_description = soup.find(
                "meta",
                attrs={"name": "description"},
            )

            description = (
                meta_description.get("content", "")
                if meta_description
                else ""
            )

    location_element = (
        soup.select_one(".jd-location p")
        or soup.select_one(".job-city")
    )

    location = (
        location_element.get_text(" ", strip=True)
        if location_element
        else None
    )

    return {
        "description": repair_mojibake(description),
        "location": repair_mojibake(location),
        "url": response.url,
        "external": is_external,
    }


def extract_jobindex_search_excerpt(job):
    html = job.get("html") or ""

    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    paragraphs = soup.select(
        ".jix_robotjob-inner p, .PaidJob-inner p, .jobsearch-result p"
    )
    excerpt = " ".join(
        paragraph.get_text(" ", strip=True)
        for paragraph in paragraphs
        if paragraph.get_text(" ", strip=True)
    )
    return repair_mojibake(excerpt)


def normalize_jobindex_job(job):
    source_id = job.get("tid")

    if not source_id:
        return None

    detail = fetch_jobindex_detail(source_id)

    company_data = job.get("company")

    if isinstance(company_data, dict):
        company_name = company_data.get("name", "")
    else:
        company_name = job.get("companytext") or ""

    location = repair_mojibake(
        detail.get("location")
        or job.get("area")
    )

    if not location:
        geojson = job.get("geojson") or {}
        features = geojson.get("features") or []

        if features:
            location = repair_mojibake(
                features[0]
                .get("properties", {})
                .get("title")
            )

    description = (
        detail.get("description")
        or extract_jobindex_search_excerpt(job)
    )

    return {
        "id": f"jobindex:{source_id}",
        "source": "jobindex",
        "sourceJobId": source_id,
        "url": detail.get("url") or f"{JOBINDEX_DETAIL_URL}/{source_id}",
        "jobTitle": repair_mojibake(job.get("headline", "")),
        "companyName": repair_mojibake(company_name),
        "companyLogo": None,
        "jobIndustry": [],
        "jobType": [],
        "jobGeo": location or "Denmark",
        "jobCountry": "Denmark",
        "jobLevel": "",
        "jobExcerpt": "",
        "jobDescription": repair_mojibake(description),
        "pubDate": job.get("firstdate"),
        "remote": False,
        "external": detail.get("external", False),
    }


def ingest_jobindex_jobs():
    jobs_by_id = {}

    for query in JOBINDEX_QUERIES:

        for page_number in range(
            1,
            JOBINDEX_MAX_PAGES + 1,
        ):
            results = fetch_jobindex_search_page(
                query,
                page_number,
            )

            if not results:
                break

            logger.info(
                "Fetched Jobindex page %s | query=%s jobs=%s",
                page_number,
                query,
                len(results),
            )

            for job in results:
                source_id = job.get("tid")

                if not source_id:
                    continue

                if source_id in jobs_by_id:
                    continue

                title = (
                    job.get("headline") or ""
                ).lower()

                is_target_role = any(
                    keyword in title
                    for keyword in ARBEITNOW_TARGET_TITLE_KEYWORDS
                )

                if not is_target_role:
                    continue

                try:
                    normalized_job = normalize_jobindex_job(job)

                except requests.RequestException as error:
                    logger.warning(
                        "Jobindex detail failed | id=%s error=%s",
                        source_id,
                        error,
                    )
                    continue

                if normalized_job:
                    jobs_by_id[source_id] = normalized_job

                time.sleep(
                    JOBINDEX_REQUEST_DELAY_SECONDS
                )

    normalized_jobs = list(jobs_by_id.values())

    logger.info(
        "Jobindex target_roles=%s",
        len(normalized_jobs),
    )

    data = {
        "source": "jobindex",
        "jobCount": len(normalized_jobs),
        "jobs": normalized_jobs,
    }

    raw_file_path = save_raw_jobs(
        data,
        "target roles",
        "jobindex",
    )

    return (
        {
            "title": "target roles",
            "industry": "jobindex",
            "path": raw_file_path,
        },
        len(normalized_jobs),
    )

def extract_job_skills(job):
    return extract_skills_from_text(clean_job_text(job))


def _normalized_heading(text):
    normalized = unescape(text).lower()
    normalized = (
        normalized
        .replace("’", "'")
        .replace("‘", "'")
        .replace("\xa0", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return re.sub(r"[\s:;,.!?–—-]+$", "", normalized)


def _heading_section(text, allow_contains=False):
    normalized = _normalized_heading(text)

    def matches(headings):
        if normalized in headings:
            return True

        if not allow_contains:
            return False

        # "plus", "bonus", "preferred" gibi tek kelimelerin normal
        # cümlelerde yanlış başlık sayılmasını engeller.
        return any(
            len(heading.split()) >= 2
            and heading in normalized
            for heading in headings
        )

    if matches(REQUIRED_HEADINGS):
        return "required"

    if matches(PREFERRED_HEADINGS):
        return "preferred"

    return None


def _is_stop_heading(text):
    normalized = _normalized_heading(text)

    if normalized in STOP_HEADINGS:
        return True

    return any(
        normalized == prefix
        or normalized.startswith(f"{prefix} ")
        for prefix in STOP_HEADING_PREFIXES
    )


def _decode_description_markup(value):
    decoded = repair_mojibake(value or "")

    # &lt;h4&gt; veya &amp;lt;h4&amp;gt; biçimlerini çözer.
    for _ in range(3):
        candidate = unescape(decoded)

        if candidate == decoded:
            break

        decoded = candidate

    return decoded


def _split_inline_section_headings(text):
    text = (
        text
        .replace("’", "'")
        .replace("‘", "'")
        .replace("\xa0", " ")
    )

    marker_pattern = "|".join(
        re.escape(marker)
        for marker in sorted(
            INLINE_SECTION_HEADINGS,
            key=len,
            reverse=True,
        )
    )

    text = re.sub(
        rf"(?<!\w)({marker_pattern})(?!\w)",
        lambda match: f"\n{match.group(0)}\n",
        text,
        flags=re.IGNORECASE,
    )

    # Restore boundaries lost by ATS pages that flatten headings, bullets and
    # short requirement lines into one continuous string.
    text = re.sub(r"\s*[•·▪]\s*", "\n", text)
    text = re.sub(
        r"(?<!e\.g\.)(?<!i\.e\.)(?<!etc\.)(?<=[.!?])\s+(?=[A-ZÆØÅ])",
        "\n",
        text,
    )
    text = re.sub(
        r"\s+(?=(?:Experience|Strong|Solid|Understanding|Knowledge|"
        r"Proficiency|Familiarity|Hands-on|Demonstrated|Ability to)\b)",
        "\n",
        text,
    )
    return text


def _append_requirement_line(
    line,
    section,
    required_text,
    secondary_required_text,
    preferred_text,
    required_skill_groups,
):
    line_lower = line.lower()

    if (
        section == "preferred"
        or any(
            marker in line_lower
            for marker in PREFERRED_LINE_MARKERS
        )
    ):
        preferred_text.append(line)
        return

    if any(marker in line_lower for marker in SECONDARY_MARKERS):
        secondary_required_text.append(line)
        return

    if section == "required":
        alternative_group = extract_alternative_skill_group(line)

        if alternative_group:
            if alternative_group not in required_skill_groups:
                required_skill_groups.append(alternative_group)

    required_text.append(line)

def extract_alternative_skill_group(text):
    text_lower = text.lower()

    # Only inspect the actual example part inside parentheses.
    example_patterns = [
        r"\((?:e\.g\.,?|for example|such as)\s*([^)]+)\)",
    ]

    for pattern in example_patterns:
        match = re.search(pattern, text_lower)

        if not match:
            continue

        example_text = match.group(1)
        skills = extract_skills_from_text(example_text)

        # It is only an alternative group if we recognize
        # multiple alternatives.
        if len(skills) >= 2:
            return skills

    skills = extract_skills_from_text(text_lower)
    has_explicit_alternative = re.search(
        r"\b(?:or|and/or)\b",
        text_lower,
    )

    # Common ATS wording puts alternatives directly in the sentence rather
    # than inside an example block, e.g. "Fabric or a similar Azure platform"
    # or "one or more technologies like ...". Do not turn every sentence
    # containing "or" into a loose alternative group.
    if len(skills) >= 2 and (
        "one or more" in text_lower
        or "one of" in text_lower
        or "any of" in text_lower
        or " or similar " in text_lower
        or (has_explicit_alternative and len(skills) == 2)
    ):
        return skills

    return []

def extract_job_requirements(job):
    required_skill_groups = []
    description_html = _decode_description_markup(
        job.get("jobDescription", "")
    )
    soup = BeautifulSoup(description_html, "html.parser")
    required_text = []
    secondary_required_text = []
    preferred_text = []
    current_section = None
    heading_tags = {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "strong",
        "b",
    }

    for element in soup.find_all([*heading_tags, "p", "li"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue

        section = _heading_section(
            text,
            allow_contains=(
                element.name in heading_tags
                and len(text) <= 160
            ),
        )
        if section:
            current_section = section
            continue

        if _is_stop_heading(text):
            current_section = None
            continue

        if current_section:
            _append_requirement_line(
                text,
                current_section,
                required_text,
                secondary_required_text,
                preferred_text,
                required_skill_groups,
            )

    if not required_text and not secondary_required_text:
        plain_text = _split_inline_section_headings(
            soup.get_text("\n", strip=True)
        )
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in plain_text.splitlines()
            if line.strip()
        ]
        current_section = None

        for line in lines:
            section = _heading_section(line)
            if section:
                current_section = section
                continue

            if _is_stop_heading(line):
                current_section = None
                continue

            if current_section:
                _append_requirement_line(
                    line,
                    current_section,
                    required_text,
                    secondary_required_text,
                    preferred_text,
                    required_skill_groups,
                )

    required_skills = []

    for line in required_text:
        line_skills = extract_skills_from_text(line)
        line_alternative_group = extract_alternative_skill_group(line)

        for skill in line_skills:
            if (
                skill not in line_alternative_group
                and skill not in required_skills
            ):
                required_skills.append(skill)

    description_text = soup.get_text(" ", strip=True)

    return {
        "required_skills": required_skills,
        "required_skill_groups": required_skill_groups,
        "secondary_required_skills": extract_skills_from_text(
            " ".join(secondary_required_text)
        ),
        "preferred_skills": extract_skills_from_text(" ".join(preferred_text)),
        "mentioned_skills": extract_job_skills(job),
        "structured_requirement_count": (
            len(required_text)
            + len(secondary_required_text)
            + len(preferred_text)
        ),
        "description_text_length": len(description_text),
    }


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


def evaluate_role_fit(job_title):
    job_title_lower = job_title.lower()
    role_rules = [
        {
            "keywords": ["analytics engineer"],
            "role_family": "ANALYTICS_ENGINEERING",
            "role_fit": "HIGH",
        },
        {
            "keywords": ["data engineer", "data warehouse engineer"],
            "role_family": "DATA_ENGINEERING",
            "role_fit": "HIGH",
        },
        {
            "keywords": ["data architect"],
            "role_family": "DATA_ARCHITECTURE",
            "role_fit": "MEDIUM",
        },
        {
            "keywords": ["data platform", "data infrastructure"],
            "role_family": "DATA_PLATFORM",
            "role_fit": "MEDIUM",
        },
        {
            "keywords": [
                "business intelligence engineer",
                "bi engineer",
                "etl developer",
            ],
            "role_family": "BI_DATA_ENGINEERING",
            "role_fit": "MEDIUM",
        },
        {
            "keywords": [
                "data analyst",
                "business intelligence analyst",
                "bi analyst",
            ],
            "role_family": "ANALYTICS",
            "role_fit": "LOW",
        },
        {
            "keywords": [
                "data scientist",
                "machine learning engineer",
                "ai engineer",
            ],
            "role_family": "DATA_SCIENCE_ML",
            "role_fit": "LOW",
        },
    ]

    for rule in role_rules:
        if any(keyword in job_title_lower for keyword in rule["keywords"]):
            return {
                "role_family": rule["role_family"],
                "role_fit": rule["role_fit"],
                "reason": f"Matched role family: {rule['role_family']}",
            }

    return {
        "role_family": "OTHER",
        "role_fit": "LOW",
        "reason": "No target role family matched",
    }

def _experience_years_fit(description_text):
    """Map explicit candidate-experience requirements to seniority fit."""
    normalized = (
        (description_text or "")
        .replace("–", "-")
        .replace("—", "-")
    )
    signals = []

    def has_candidate_experience_context(match):
        window = normalized[
            max(0, match.start() - 80):
            min(len(normalized), match.end() + 100)
        ]

        # Do not mistake company age or benefit wording for candidate seniority.
        if re.search(
            r"\b(?:founded|company has|we have been|operating for|"
            r"in business for)\b",
            window,
        ):
            return False

        return bool(
            re.search(
                r"\b(?:experience|experienced|professional|commercial|"
                r"hands-on|working|worked|building|developing|engineering)\b",
                window,
            )
        )

    def fit_for_minimum(minimum_years):
        if minimum_years <= 2:
            return "LOW"
        if minimum_years <= 4:
            return "MEDIUM"
        return "HIGH"

    range_pattern = re.compile(
        r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:years?|yrs?)\b"
    )
    for match in range_pattern.finditer(normalized):
        if not has_candidate_experience_context(match):
            continue

        minimum_years = int(match.group(1))
        maximum_years = int(match.group(2))

        if maximum_years < minimum_years:
            continue

        if maximum_years <= 3:
            signals.append("LOW")
        elif minimum_years >= 5:
            signals.append("HIGH")
        else:
            signals.append("MEDIUM")

    minimum_pattern = re.compile(
        r"\b(?:at least|minimum(?: of)?|more than|over)\s*"
        r"(\d{1,2})\s*(?:\+\s*)?(?:years?|yrs?)\b"
    )
    for match in minimum_pattern.finditer(normalized):
        if has_candidate_experience_context(match):
            signals.append(fit_for_minimum(int(match.group(1))))

    plus_pattern = re.compile(
        r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b"
    )
    for match in plus_pattern.finditer(normalized):
        if has_candidate_experience_context(match):
            signals.append(fit_for_minimum(int(match.group(1))))

    exact_pattern = re.compile(
        r"(?<![\d-])(\d{1,2})\s*(?:years?|yrs?)\s+"
        r"(?:of\s+)?(?:relevant\s+|professional\s+|hands-on\s+)?"
        r"experience\b"
    )
    for match in exact_pattern.finditer(normalized):
        signals.append(fit_for_minimum(int(match.group(1))))

    if not signals:
        return None

    unique_signals = set(signals)

    # Conflicting requirements should be reviewed instead of auto-skipped.
    if len(unique_signals) > 1:
        return "MEDIUM"

    return signals[0]


def evaluate_seniority_fit(job):
    title = (job.get("jobTitle") or "").lower()
    level = (job.get("jobLevel") or "").lower()
    description_text = clean_job_text(job)

    below_target_terms = [
        "junior",
        "intern",
        "internship",
        "working student",
        "werkstudent",
        "graduate",
        "trainee",
    ]

    if any(term in title for term in below_target_terms):
        return "LOW"

    if "principal" in title:
        return "STRETCH"

    if "staff" in title or "lead" in title:
        return "MEDIUM"

    title_is_target_level = (
        "senior" in title
        or "experienced" in title
    )

    level_is_target_level = level in {
        "senior",
        "midweight",
        "mid-level",
    }

    if level in {
        "junior",
        "intern",
        "internship",
        "entry-level",
        "entry level",
    }:
        return "LOW"

    experience_fit = _experience_years_fit(description_text)

    if title_is_target_level or level_is_target_level:
        # A senior title combined with a clearly junior experience band is
        # internally inconsistent and should be reviewed, not auto-applied.
        if experience_fit == "LOW":
            return "MEDIUM"
        return "HIGH"

    if experience_fit:
        return experience_fit

    if re.search(
        r"\b(?:step up|grow|progress)\s+(?:in)?to\s+(?:a\s+)?senior\b",
        description_text,
    ):
        return "MEDIUM"

    experienced_role_patterns = [
        r"\b(?:looking|searching|seeking|hiring)\s+(?:for\s+)?"
        r"(?:an?\s+)?experienced\s+"
        r"(?:data|analytics|platform|business intelligence)\s+"
        r"(?:engineer|architect)\b",
        r"\b(?:you(?:'re| are)|as)\s+an?\s+experienced\s+"
        r"(?:data|analytics|platform|business intelligence)\s+"
        r"(?:engineer|architect)\b",
        r"\berfaren\s+(?:data|analytics|platform)\s+"
        r"(?:engineer|arkitekt)\b",
    ]

    if any(
        re.search(pattern, description_text)
        for pattern in experienced_role_patterns
    ):
        return "HIGH"

    return "UNKNOWN"


def evaluate_location_fit(job):
    geo = repair_mojibake(job.get("jobGeo") or "").lower().strip()
    source = (job.get("source") or "").lower()

    geo = re.sub(r"\s*[-–—]\s*", " ", geo)
    geo = re.sub(r"\s+", " ", geo)

    # Location bilgisi yoksa otomatik eleme.
    if not geo or geo in {"unknown", "remote", "homeoffice"}:
        return "REVIEW"

    # Jobindex esas olarak Denmark ilanları getiriyor.
    # Bilinen yabancı ülke/lokasyon yoksa Denmark kabul et.
    if source == "jobindex":
        foreign_terms = [
            "germany",
            "deutschland",
            "netherlands",
            "belgium",
            "france",
            "switzerland",
            "sweden",
            "norway",
            "finland",
            "united kingdom",
            "england",
            "london",
            "paris",
            "amsterdam",
            "berlin",
            "hamburg",
            "munich",
            "münchen",
            "zurich",
            "zürich",
            "stockholm",
            "oslo",
            "brussels",
        ]

        if not any(term in geo for term in foreign_terms):
            return "APPLY"

    # Denmark: relocation gerekmeyen doğrudan target.
    denmark_terms = [
        "denmark",
        "danmark",
        "copenhagen",
        "københavn",
        "aarhus",
        "odense",
        "aalborg",
    ]

    if any(term in geo for term in denmark_terms):
        return "APPLY"

    # Target countries where relocation may be required.
    relocation_target_terms = [
        "germany",
        "deutschland",
        "berlin",
        "hamburg",
        "munich",
        "münchen",
        "cologne",
        "köln",
        "frankfurt",
        "stuttgart",
        "düsseldorf",
        "dusseldorf",

        "netherlands",
        "holland",
        "amsterdam",
        "rotterdam",
        "utrecht",
        "eindhoven",
        "the hague",
        "den haag",

        "belgium",
        "brussels",
        "bruxelles",
        "antwerp",
        "antwerpen",
        "ghent",
        "gent",
        "leuven",
    ]

    if any(term in geo for term in relocation_target_terms):
        return "REVIEW"

    broad_remote_terms = [
        "anywhere",
        "worldwide",
        "global",
        "remote europe",
        "europe remote",
        "europe",
        "european union",
        "remote eu",
        "remote eea",
    ]

    if any(term in geo for term in broad_remote_terms):
        return "APPLY"

    if "emea" in geo:
        return "REVIEW"

    return "SKIP"


def detect_posting_language(job):
    text = clean_job_text(job)
    if len(text) < 100:
        return {
            "posting_language": "UNKNOWN",
            "language_confidence": None,
        }

    try:
        detected = detect_langs(text)[0]
    except LangDetectException:
        return {
            "posting_language": "UNKNOWN",
            "language_confidence": None,
        }

    language_map = {
        "en": "ENGLISH",
        "da": "DANISH",
        "nl": "DUTCH",
        "de": "GERMAN",
        "fr": "FRENCH",
    }
    return {
        "posting_language": language_map.get(detected.lang, "OTHER"),
        "language_confidence": round(detected.prob, 2),
    }


def evaluate_language_fit(job):
    text = clean_job_text(job)
    posting_language = detect_posting_language(job)
    local_languages = ["danish", "dutch", "german", "french", "flemish"]
    required_languages = []
    preferred_languages = []
    not_required_languages = []

    for language in local_languages:
        english_alternative_patterns = [
            rf"\b{language}\b\s+or\s+english\b",
            rf"\benglish\b\s+or\s+{language}\b",
        ]
        not_required_patterns = [
            rf"\b{language}\b.{{0,30}}"
            rf"(?:is\s+not|isn't|isn’t|not)\s+"
            rf"(?:required|mandatory|essential|needed|necessary|"
            rf"a\s+requirement)\b",
            rf"\b(?:no|without)\s+{language}\b.{{0,20}}"
            rf"\b(?:required|requirement|needed|necessary)\b",
            rf"\b(?:do\s+not|don't|don’t)\s+(?:need|require)\s+"
            rf"(?:to\s+(?:speak|know|understand)\s+)?{language}\b",
        ]
        required_patterns = [
            rf"\b{language}\b.{{0,40}}\b(required|mandatory|essential)\b",
            rf"\b(required|mandatory|essential)\b.{{0,40}}\b{language}\b",
            rf"\b(fluent|fluency|native)\b.{{0,30}}\b{language}\b",
            rf"\bmust\b.{{0,30}}\b(speak|know|understand)\b.{{0,30}}\b{language}\b",
        ]
        preferred_patterns = [
            rf"\b{language}\b.{{0,40}}\b(preferred|advantage|plus|beneficial)\b",
            rf"\b(preferred|advantage|plus|beneficial)\b.{{0,40}}\b{language}\b",
            rf"\bnice to have\b.{{0,40}}\b{language}\b",
        ]
        has_english_alternative = any(
            re.search(pattern, text) for pattern in english_alternative_patterns
        )
        is_explicitly_not_required = any(
            re.search(pattern, text) for pattern in not_required_patterns
        )

        if is_explicitly_not_required:
            not_required_languages.append(language)

        if (
            not has_english_alternative
            and not is_explicitly_not_required
            and any(
                re.search(pattern, text)
                for pattern in required_patterns
            )
        ):
            required_languages.append(language)
        elif any(re.search(pattern, text) for pattern in preferred_patterns):
            preferred_languages.append(language)

    result = {
        "posting_lang": posting_language["posting_language"],
        "language_confidence": posting_language["language_confidence"],
        "required_languages": required_languages,
        "preferred_languages": preferred_languages,
        "not_required_languages": not_required_languages,
    }

    if required_languages:
        return {
            **result,
            "language_fit": "FAIL",
            "reason": f"Required local language: {', '.join(required_languages)}",
        }
    if preferred_languages:
        return {
            **result,
            "language_fit": "PASS",
            "reason": (
                "Local language is preferred but not required: "
                f"{', '.join(preferred_languages)}"
            ),
        }
    if not_required_languages:
        return {
            **result,
            "language_fit": "PASS",
            "reason": (
                "Local language is explicitly not required: "
                f"{', '.join(not_required_languages)}"
            ),
        }
    if posting_language["posting_language"] not in {
        "DANISH",
        "ENGLISH",
        "UNKNOWN",
    }:
        return {
            **result,
            "language_fit": "FAIL",
            "reason": "Posting language is neither Danish nor English",
        }

    if posting_language["posting_language"] == "DANISH":
        return {
            **result,
            "language_fit": "REVIEW",
            "reason": (
                "The posting is written in Danish, but no explicit English "
                "working-language alternative was found"
            ),
        }

    return {
        **result,
        "language_fit": "UNKNOWN",
        "reason": "No explicit local-language requirement found",
    }


def evaluate_work_authorization(job):
    text = clean_job_text(job)
    no_sponsorship_patterns = [
        "no visa sponsorship",
        "visa sponsorship is not available",
        "unable to sponsor",
        "cannot sponsor",
        "we do not sponsor",
        "without sponsorship",
    ]
    existing_authorization_patterns = [
        "must have the right to work",
        "must already have the right to work",
        "must be authorized to work",
        "must already be authorized to work",
        "existing work authorization",
        "eu citizens only",
        "eea citizens only",
    ]
    sponsorship_available_patterns = [
        "visa sponsorship available",
        "visa sponsorship is available",
        "we sponsor visas",
        "work permit sponsorship",
        "sponsorship provided",
        "visa support available",
    ]

    for phrase in no_sponsorship_patterns:
        if phrase in text:
            return {
                "work_authorization_fit": "FAIL",
                "authorization_signal": "NO_SPONSORSHIP",
                "reason": f"Employer states no sponsorship: '{phrase}'",
            }
    for phrase in existing_authorization_patterns:
        if phrase in text:
            return {
                "work_authorization_fit": "FAIL",
                "authorization_signal": "EXISTING_AUTH_REQUIRED",
                "reason": f"Existing work authorization required: '{phrase}'",
            }
    for phrase in sponsorship_available_patterns:
        if phrase in text:
            return {
                "work_authorization_fit": "PASS",
                "authorization_signal": "SPONSORSHIP_AVAILABLE",
                "reason": f"Employer indicates sponsorship support: '{phrase}'",
            }

    return {
        "work_authorization_fit": "UNKNOWN",
        "authorization_signal": "UNKNOWN",
        "reason": "No explicit work authorization or sponsorship information found",
    }


def evaluate_technical_fit(job):
    requirements = extract_job_requirements(job)

    required_skills = requirements["required_skills"]
    required_skill_groups = requirements["required_skill_groups"]
    secondary_required_skills = requirements["secondary_required_skills"]
    preferred_skills = requirements["preferred_skills"]

    matched_required = [
        skill
        for skill in required_skills
        if skill in CANDIDATE_SKILLS
    ]

    growth_required = [
        skill
        for skill in required_skills
        if skill in CANDIDATE_GROWTH_SKILLS
    ]

    missing_required = [
        skill
        for skill in required_skills
        if skill not in CANDIDATE_SKILLS
        and skill not in CANDIDATE_GROWTH_SKILLS
    ]

    matched_required_groups = []
    growth_required_groups = []
    missing_required_groups = []

    for group in required_skill_groups:
        matched = [
            skill
            for skill in group
            if skill in CANDIDATE_SKILLS
        ]

        growth = [
            skill
            for skill in group
            if skill in CANDIDATE_GROWTH_SKILLS
        ]

        if matched:
            matched_required_groups.append(
                {
                    "alternatives": group,
                    "matched_by": matched,
                }
            )

        elif growth:
            growth_required_groups.append(
                {
                    "alternatives": group,
                    "matched_by": growth,
                }
            )

        else:
            missing_required_groups.append(group)

    matched_secondary = [
        skill
        for skill in secondary_required_skills
        if skill in CANDIDATE_SKILLS
    ]

    growth_secondary = [
        skill
        for skill in secondary_required_skills
        if skill in CANDIDATE_GROWTH_SKILLS
    ]

    missing_secondary = [
        skill
        for skill in secondary_required_skills
        if skill not in CANDIDATE_SKILLS
        and skill not in CANDIDATE_GROWTH_SKILLS
    ]

    matched_preferred = [
        skill
        for skill in preferred_skills
        if skill in CANDIDATE_SKILLS
    ]

    growth_preferred = [
        skill
        for skill in preferred_skills
        if skill in CANDIDATE_GROWTH_SKILLS
    ]

    missing_preferred = [
        skill
        for skill in preferred_skills
        if skill not in CANDIDATE_SKILLS
        and skill not in CANDIDATE_GROWTH_SKILLS
    ]

    mentioned_skills = requirements["mentioned_skills"]
    structured_requirement_count = requirements[
        "structured_requirement_count"
    ]
    description_text_length = requirements[
        "description_text_length"
    ]

    total_core_requirements = (
        len(required_skills)
        + len(required_skill_groups)
    )

    matched_core = (
        len(matched_required)
        + len(matched_required_groups)
    )

    growth_core = (
        len(growth_required)
        + len(growth_required_groups)
    )

    if total_core_requirements:
        core_coverage = (
            matched_core
            + 0.5 * growth_core
        ) / total_core_requirements
    else:
        core_coverage = None

    if total_core_requirements:
        technical_evidence_status = "PARSED"
    elif preferred_skills:
        technical_evidence_status = "PREFERRED_ONLY"
    elif secondary_required_skills:
        technical_evidence_status = "SECONDARY_ONLY"
    elif description_text_length < MIN_REQUIREMENT_DESCRIPTION_LENGTH:
        technical_evidence_status = "INSUFFICIENT_DESCRIPTION"
    elif structured_requirement_count:
        technical_evidence_status = "NO_TRACKED_CORE_SKILLS"
    elif mentioned_skills:
        technical_evidence_status = "REQUIREMENTS_PARSE_FAILED"
    else:
        technical_evidence_status = "NO_EXPLICIT_TECH_REQUIREMENTS"

    if core_coverage is None:
        fit = "UNKNOWN"

        reason_by_status = {
            "PREFERRED_ONLY": (
                "Only preferred technical skills were found; no mandatory "
                "technical baseline was stated"
            ),
            "SECONDARY_ONLY": (
                "Only secondary technical requirements were found; no core "
                "technical baseline was stated"
            ),
            "INSUFFICIENT_DESCRIPTION": (
                "The stored job description is too short to evaluate "
                "technical requirements reliably"
            ),
            "NO_TRACKED_CORE_SKILLS": (
                "A requirement section was found, but it contains no tracked "
                "core technical skills"
            ),
            "REQUIREMENTS_PARSE_FAILED": (
                "Technical skills occur in the description, but no recognized "
                "requirement section was extracted"
            ),
            "NO_EXPLICIT_TECH_REQUIREMENTS": (
                "No explicit technical requirements were found"
            ),
        }
        reason = reason_by_status[technical_evidence_status]

    elif core_coverage < 0.6:
        fit = "LOW"

        gaps = list(
            missing_required
            + growth_required
        )

        for group in missing_required_groups:
            gaps.append(" / ".join(group))

        for group in growth_required_groups:
            gaps.append(
                " / ".join(group["alternatives"])
            )

        reason = (
            "Major gaps in core required skills: "
            + ", ".join(gaps)
        )

    elif (
        missing_required
        or growth_required
        or missing_required_groups
        or growth_required_groups
    ):
        fit = "MEDIUM"
        reason = (
            "Core role is partially matched, but some required skills "
            "are missing or still growth areas"
        )

    elif missing_secondary:
        fit = "MEDIUM"
        reason = (
            "Core required skills are matched, but some secondary "
            "requirements are missing"
        )

    else:
        fit = "HIGH"
        reason = "Core technical requirements are strongly matched"

    return {
        "technical_fit": fit,
        "technical_evidence_status": technical_evidence_status,
        "description_text_length": description_text_length,
        "structured_requirement_count": structured_requirement_count,
        "mentioned_skills": mentioned_skills,

        "required_skills": required_skills,
        "matched_required_skills": matched_required,
        "growth_required_skills": growth_required,
        "missing_required_skills": missing_required,

        "required_skill_groups": required_skill_groups,
        "matched_required_groups": matched_required_groups,
        "growth_required_groups": growth_required_groups,
        "missing_required_groups": missing_required_groups,

        "secondary_required_skills": secondary_required_skills,
        "matched_secondary_skills": matched_secondary,
        "growth_secondary_skills": growth_secondary,
        "missing_secondary_skills": missing_secondary,

        "preferred_skills": preferred_skills,
        "matched_preferred_skills": matched_preferred,
        "growth_preferred_skills": growth_preferred,
        "missing_preferred_skills": missing_preferred,

        "core_coverage": (
            round(core_coverage, 2)
            if core_coverage is not None
            else None
        ),

        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Decision and pipeline orchestration
# ---------------------------------------------------------------------------


def make_decision(
    role,
    seniority,
    location,
    language,
    authorization,
    technical,
):
    skip_reasons = []

    if role["role_fit"] == "LOW":
        skip_reasons.append(role["reason"])
    if seniority == "LOW":
        skip_reasons.append("Seniority is below the target level")
    if location == "SKIP":
        skip_reasons.append("Location is outside the target scope")
    if language["language_fit"] == "FAIL":
        skip_reasons.append(language["reason"])
    if authorization["work_authorization_fit"] == "FAIL":
        skip_reasons.append(authorization["reason"])
    if technical["technical_fit"] == "LOW":
        skip_reasons.append(technical["reason"])

    if skip_reasons:
        return {"decision": "SKIP", "reasons": skip_reasons}

    review_reasons = []

    if role["role_fit"] == "MEDIUM":
        review_reasons.append(role["reason"])
    if seniority in {"MEDIUM", "STRETCH"}:
        review_reasons.append(f"Seniority fit requires review: {seniority}")
    if location == "REVIEW":
        review_reasons.append("Regional location requires review")
    if language["language_fit"] == "REVIEW":
        review_reasons.append(language["reason"])
    if (
        authorization["work_authorization_fit"] == "REVIEW"
        and location != "APPLY"
    ):
        review_reasons.append(authorization["reason"])
    if technical["technical_fit"] in {"UNKNOWN", "MEDIUM"}:
        review_reasons.append(technical["reason"])

    if review_reasons:
        return {"decision": "REVIEW", "reasons": review_reasons}

    return {
        "decision": "APPLY",
        "reasons": ["No blocking or unresolved fit signals found"],
    }


def evaluate_job(job):
    role = evaluate_role_fit(job.get("jobTitle", ""))
    seniority = evaluate_seniority_fit(job)
    location = evaluate_location_fit(job)
    language = evaluate_language_fit(job)
    authorization = evaluate_work_authorization(job)
    technical = evaluate_technical_fit(job)
    decision = make_decision(
        role,
        seniority,
        location,
        language,
        authorization,
        technical,
    )

    return {
        **job,
        "evaluation": {
            "role": role,
            "seniority_fit": seniority,
            "location_fit": location,
            "language": language,
            "work_authorization": authorization,
            "technical": technical,
        },
        "decision": decision["decision"],
        "decision_reasons": decision["reasons"],
    }


def save_evaluated_jobs(evaluated_jobs):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_directory = Path("data/processed")
    output_directory.mkdir(parents=True, exist_ok=True)
    file_path = output_directory / f"evaluated_jobs_{timestamp}.json"

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(evaluated_jobs, file, indent=4, ensure_ascii=False)

    return str(file_path)


def save_run_metadata(
    total_fetched,
    unique_jobs,
    apply_jobs,
    review_jobs,
    skip_jobs,
    run_id,
    source_counts,
):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    metadata = {
        "run_timestamp": timestamp,
        "total_fetched": total_fetched,
        "unique_jobs": unique_jobs,
        "apply_jobs": apply_jobs,
        "review_jobs": review_jobs,
        "skip_jobs": skip_jobs,
        "source_counts": source_counts,
        "airflow_run_id": run_id,
    }
    output_directory = Path("data/run_metadata")
    output_directory.mkdir(parents=True, exist_ok=True)
    file_path = output_directory / f"run_{timestamp}.json"

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4, ensure_ascii=False)

    return str(file_path)


def transform_jobs(raw_files):
    raw_batches = []

    for raw_file in raw_files:
        with Path(raw_file["path"]).open(encoding="utf-8") as file:
            data = json.load(file)

        raw_batches.append(
            {
                "title": raw_file["title"],
                "industry": raw_file["industry"],
                "jobs": data.get("jobs", []),
            }
        )

    all_jobs = process_jobs(raw_batches)
    evaluated_jobs = [evaluate_job(job) for job in all_jobs]
    decision_buckets = {"APPLY": [], "REVIEW": [], "SKIP": []}

    for job in evaluated_jobs:
        decision_buckets[job["decision"]].append(job)

    save_evaluated_jobs(evaluated_jobs)

    return all_jobs, evaluated_jobs, decision_buckets
