import unittest
from unittest.mock import Mock, patch

import requests

from job_market_intelligence.job_api_client import (
    evaluate_language_fit,
    evaluate_location_fit,
    extract_job_requirements,
    fetch_jobindex_search_page,
    normalize_jobicy_job,
    process_jobs,
    repair_mojibake,
)


class NormalizationTests(unittest.TestCase):
    def test_jobicy_job_gets_namespaced_identity_and_source(self):
        normalized = normalize_jobicy_job({"id": 123, "jobTitle": "Data Engineer"})

        self.assertEqual(normalized["id"], "jobicy:123")
        self.assertEqual(normalized["source"], "jobicy")
        self.assertEqual(normalized["sourceJobId"], 123)

    def test_mojibake_is_repaired(self):
        self.assertEqual(repair_mojibake("KÃ¸benhavn"), "København")

    def test_duplicate_queries_are_merged(self):
        batches = [
            {"title": "data engineer", "industry": "engineering", "jobs": [{"id": "x"}]},
            {"title": "analytics engineer", "industry": "engineering", "jobs": [{"id": "x"}]},
        ]

        jobs = process_jobs(batches)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(
            jobs[0]["matched_query_titles"],
            ["data engineer", "analytics engineer"],
        )


class EvaluatorRegressionTests(unittest.TestCase):
    def test_non_city_danish_location_is_accepted_for_jobindex(self):
        self.assertEqual(
            evaluate_location_fit({"source": "jobindex", "jobGeo": "Birkerød"}),
            "APPLY",
        )

    def test_foreign_jobindex_location_requires_review(self):
        self.assertEqual(
            evaluate_location_fit({"source": "jobindex", "jobGeo": "Berlin"}),
            "REVIEW",
        )

    def test_explicit_danish_requirement_fails(self):
        job = {"jobDescription": "You must speak fluent Danish. " * 10}
        self.assertEqual(evaluate_language_fit(job)["language_fit"], "FAIL")

    def test_english_alternative_does_not_fail(self):
        job = {"jobDescription": "You may work in Danish or English. " * 10}
        self.assertNotEqual(evaluate_language_fit(job)["language_fit"], "FAIL")

    @patch(
        "job_market_intelligence.job_api_client.detect_posting_language",
        return_value={"posting_language": "DANISH", "language_confidence": 0.99},
    )
    def test_danish_posting_without_language_evidence_requires_review(
        self,
        _mock_detect,
    ):
        job = {"jobDescription": "A sufficiently long neutral description. " * 10}
        self.assertEqual(evaluate_language_fit(job)["language_fit"], "REVIEW")

    def test_encoded_requirement_markup_is_extracted(self):
        job = {
            "jobDescription": (
                "&lt;h3&gt;What we are looking for&lt;/h3&gt;"
                "&lt;ul&gt;&lt;li&gt;Strong SQL and dbt experience&lt;/li&gt;&lt;/ul&gt;"
            )
        }

        requirements = extract_job_requirements(job)

        self.assertEqual(requirements["required_skills"], ["sql", "dbt"])
        self.assertEqual(requirements["structured_requirement_count"], 1)


class SourceFailureTests(unittest.TestCase):
    @patch("job_market_intelligence.job_api_client.time.sleep")
    @patch("job_market_intelligence.job_api_client.requests.get")
    def test_jobindex_failure_is_not_reported_as_empty_success(
        self,
        mock_get,
        _mock_sleep,
    ):
        response = Mock(status_code=503, url="https://example.invalid")
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        mock_get.return_value = response

        with self.assertRaises(RuntimeError):
            fetch_jobindex_search_page('"data engineer"', 1)

        self.assertEqual(mock_get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
