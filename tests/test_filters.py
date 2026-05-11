#!/usr/bin/env python3
import pytest
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsi_scraper_elite import TextClassifier, ScoringEngine, JobRecord, VALID_HEADCOUNT_BUCKETS

class TestLocationRestrictionFilter:
    @pytest.mark.parametrize("text", [
        "Remote, Germany", "Remote in Europe", "Remote US only", "United States",
        "Canada", "UK", "EMEA", "LATAM", "APAC", "North America", "Remote North America",
        "Must be based in Spain", "Must reside in Canada", "Work authorization required",
        "Visa sponsorship not available", "Hybrid role with office in London",
        "Onsite position in Berlin",
    ])
    def test_rejects_location_restricted(self, text):
        assert TextClassifier.has_location_restriction(text) is True
    
    @pytest.mark.parametrize("text", [
        "Work from anywhere in the world",
        "Remote worldwide - no location restrictions",
        "Globally distributed team, hire from anywhere",
        "Open to candidates worldwide, timezone flexible",
    ])
    def test_accepts_unrestricted(self, text):
        assert TextClassifier.has_location_restriction(text) is False

class TestRemoteProofFilter:
    @pytest.mark.parametrize("text", [
        "Remote position", "Fully remote", "Remote first company",
        "Distributed team", "Work from home", "Flexible location",
    ])
    def test_rejects_weak_remote_only(self, text):
        assert TextClassifier.has_strong_global_remote(text) is False
        assert TextClassifier.has_weak_remote_only(text) is True
    
    @pytest.mark.parametrize("text", [
        "Worldwide remote", "Remote Worldwide", "Work from anywhere",
        "Anywhere in the world", "Global remote position", "Open globally",
        "No location restriction", "Location independent role",
        "Globally distributed team", "Open to candidates worldwide",
    ])
    def test_accepts_strong_global_proof(self, text):
        assert TextClassifier.has_strong_global_remote(text) is True

class TestRoleFilter:
    @pytest.mark.parametrize("title,description,expected_family", [
        ("Backend Engineer", "Python, Django, PostgreSQL", "backend"),
        ("Senior Frontend Developer", "React, TypeScript", "frontend"),
        ("Full Stack Engineer", "Node.js and React", "fullstack"),
        ("iOS Developer", "Swift, mobile apps", "mobile"),
        ("DevOps Engineer", "Kubernetes, AWS, Terraform", "devops"),
        ("Cloud Platform Engineer", "GCP, infrastructure", "cloud"),
        ("Site Reliability Engineer", "SRE, monitoring", "sre"),
        ("QA Automation Engineer", "Selenium, test automation", "qa automation"),
        ("Data Engineer", "Spark, Airflow, pipelines", "data engineering"),
        ("Machine Learning Engineer", "PyTorch, model deployment", "ai ml"),
        ("Security Engineer", "Application security, cloud security", "security engineering"),
        ("Software Engineer", "General backend development", "software engineering"),
    ])
    def test_accepts_engineering_roles(self, title, description, expected_family):
        result = TextClassifier.classify_role_family(title, description)
        assert result == expected_family
    
    @pytest.mark.parametrize("title,description", [
        ("Customer Support Engineer", "Help customers with technical issues"),
        ("Sales Engineer", "Pre-sales technical consulting"),
        ("Engineering Manager", "Lead a team of engineers"),
        ("Recruiter", "Source engineering talent"),
        ("Intern Software Developer", "Learning opportunity for students"),
        ("Technical Writer", "Write API documentation"),
        ("IT Support Specialist", "Helpdesk and troubleshooting"),
    ])
    def test_rejects_non_engineering_roles(self, title, description):
        result = TextClassifier.classify_role_family(title, description)
        assert result is None

class TestScoringEngine:
    def test_minimum_score_required(self):
        job = JobRecord(
            company_name="Test Co", company_domain="test.com", company_website="https://test.com",
            company_headcount_bucket="51 to 100", company_hq_country="United States",
            target_market_fit="high", job_title="Backend Engineer", role_family="backend",
            seniority="mid", location_raw="Worldwide", remote_proof="strong_global",
            restriction_check="none_found", job_url="https://test.com/jobs/1",
            final_canonical_url="https://test.com/jobs/1",
            posted_date=(datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d"),
            days_old=3, source_name="Test Source", source_family="greenhouse",
            source_type="ats_api", source_trust_score=90, tech_stack_detected="python,aws",
            dsi_icp_score=0, score_reasons="", duplicate_key="test:backend-engineer"
        )
        
        full_text = "Backend Engineer - Work from anywhere in the world. No location restrictions. Python, AWS."
        score, reasons = ScoringEngine.calculate(job, full_text)
        
        assert score >= 85, f"Expected score >= 85, got {score}"
        assert "Strong global remote proof" in reasons
        assert "Headcount verified" in reasons
