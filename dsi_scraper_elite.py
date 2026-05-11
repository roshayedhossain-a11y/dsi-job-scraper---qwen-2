#!/usr/bin/env python3
"""
DSI Innovators Elite Job Collector
Production-grade GitHub Actions data collector for strict ICP buying intent.
"""

import os
import re
import sys
import json
import time
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set, Tuple, Any
from urllib.parse import urlparse
from dataclasses import dataclass, field, asdict
import warnings

warnings.filterwarnings("ignore")

import requests
import pandas as pd
import yaml
import tldextract
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from rapidfuzz import fuzz
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# =============================================================================
# CONFIGURATION
# =============================================================================

TARGET_MARKETS = {
    "United States", "Canada", "United Kingdom", "Ireland", "Australia", 
    "New Zealand", "Singapore", "Netherlands", "Germany", "Switzerland",
    "Sweden", "Norway", "Denmark", "Finland", "UAE"
}

VALID_HEADCOUNT_BUCKETS = {"10 to 50", "51 to 100", "101 to 200"}

STRONG_GLOBAL_SIGNALS = [
    r'worldwide', r'remote worldwide', r'work from anywhere', r'anywhere in the world',
    r'remote anywhere', r'global remote', r'open globally', r'open to candidates worldwide',
    r'no location restriction', r'location independent', r'globally distributed team',
    r'fully distributed team', r'hire from anywhere', r'all countries', r'any country',
    r'wherever you are', r'work remotely from anywhere'
]

WEAK_REMOTE_SIGNALS = [
    r'\bremote\b', r'fully remote', r'remote first', r'\bdistributed\b',
    r'\basync\b', r'home office', r'\bvirtual\b', r'flexible location'
]

LOCATION_REJECT_PATTERNS = [
    r'united states only', r'us only', r'usa only', r'canada only', r'uk only',
    r'europe only', r'eu only', r'emea only', r'apac only', r'latam only',
    r'north america only', r'australia only', r'new zealand only', r'india only',
    r'remote in united states', r'remote in canada', r'remote in europe',
    r'remote in uk', r'remote in germany', r'remote in spain', r'remote in poland',
    r'remote in portugal', r'remote in romania', r'remote in serbia', r'remote in ukraine',
    r'remote north america', r'remote latam', r'remote emea', r'remote apac',
    r'must be based in', r'must live in', r'must reside in', r'must be located in',
    r'applicants must be based in', r'applicants must reside in',
    r'work authorization required', r'must be authorized to work',
    r'legally authorized to work', r'right to work in', r'eligible to work in',
    r'no visa sponsorship', r'visa sponsorship not available', r'cannot sponsor',
    r'unable to sponsor', r'citizen only', r'permanent resident only',
    r'\bhybrid\b', r'\bonsite\b', r'office required', r'must commute'
]

ACCEPTED_ROLE_FAMILIES = {
    'backend', 'frontend', 'fullstack', 'mobile', 'devops', 'cloud', 
    'sre', 'qa automation', 'data engineering', 'ai ml', 'platform', 
    'security engineering', 'software engineering'
}

ROLE_FAMILY_MAP = {
    r'backend.*engineer': 'backend', r'backend.*developer': 'backend',
    r'python.*developer': 'backend', r'java.*developer': 'backend',
    r'ruby.*developer': 'backend', r'php.*developer': 'backend',
    r'golang.*developer': 'backend', r'go.*developer': 'backend',
    r'node\.js.*developer': 'backend', r'nodejs.*developer': 'backend',
    r'frontend.*engineer': 'frontend', r'front-end.*engineer': 'frontend',
    r'ui.*engineer': 'frontend', r'react.*developer': 'frontend',
    r'vue.*developer': 'frontend', r'angular.*developer': 'frontend',
    r'full.*stack.*engineer': 'fullstack', r'fullstack.*engineer': 'fullstack',
    r'full.*stack.*developer': 'fullstack', r'fullstack.*developer': 'fullstack',
    r'mobile.*engineer': 'mobile', r'android.*engineer': 'mobile',
    r'ios.*engineer': 'mobile', r'mobile.*developer': 'mobile',
    r'devops.*engineer': 'devops', r'platform.*engineer': 'platform',
    r'cloud.*engineer': 'cloud', r'site.*reliability.*engineer': 'sre',
    r'\bsre\b': 'sre',
    r'qa.*automation.*engineer': 'qa automation', r'sdet': 'qa automation',
    r'quality.*assurance.*automation': 'qa automation',
    r'data.*engineer': 'data engineering',
    r'ai.*engineer': 'ai ml', r'machine.*learning.*engineer': 'ai ml',
    r'ml.*engineer': 'ai ml',
    r'security.*engineer': 'security engineering',
    r'application.*security.*engineer': 'security engineering',
    r'software.*engineer': 'software engineering',
    r'software.*developer': 'software engineering',
}

REJECTED_ROLE_PATTERNS = [
    r'customer.*support', r'technical.*support', r'solutions.*engineer',
    r'sales.*engineer', r'pre.?sales', r'engineering.*manager',
    r'product.*manager', r'project.*manager', r'scrum.*master',
    r'business.*analyst', r'data.*analyst', r'ux.*designer', r'ui.*designer',
    r'graphic.*designer', r'recruiter', r'talent.*acquisition',
    r'\bintern\b', r'\bstudent\b', r'\btrainee\b', r'\bapprentice\b',
    r'business.*developer', r'\bmarketing\b', r'\bsales\b', r'\boperations\b',
    r'\bfinance\b', r'\blegal\b', r'\bhr\b', r'technical.*writer',
    r'it.*support', r'helpdesk'
]

TITLE_NOISE_WORDS = [
    'senior', 'sr', 'lead', 'principal', 'staff', 'junior', 'mid',
    'remote', 'worldwide', 'global', 'contract', 'full.?time', 'part.?time'
]

COMPANY_NORMALIZE_PATTERNS = [
    r'\s+Inc\.?$', r'\s+LLC\.?$', r'\s+Ltd\.?$', r'\s+Limited\.?$',
    r'\s+GmbH\.?$', r'\s+BV\.?$', r'\s+Pty\.?$', r'\s+Co\.?$',
    r'\s+Company\.?$', r'\s+Corp\.?$', r'\s+Corporation\.?$',
    r'^The\s+', r'\s+Technologies?$', r'\s+Systems?$', r'\s+Labs?$'
]

SCORING = {
    'proven_remote_worldwide': 30,
    'no_restriction_found': 15,
    'timezone_flexible': 5,
    'headcount_valid': 20,
    'target_market_fit': 10,
    'core_engineering_role': 15,
    'fresh_0_7_days': 10,
    'fresh_8_14_days': 7,
    'fresh_15_21_days': 5,
    'official_ats_source': 10,
    'trusted_board_match': 6,
    'multiple_roles_same_company': 5,
    'product_saas_company': 5
}

MIN_ACCEPT_SCORE = 85
MAX_JOB_AGE_DAYS = 21
RATE_LIMIT_PER_DOMAIN = 1.0
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
JITTER_RANGE = 0.3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SourceDefinition:
    source_id: str
    source_name: str
    source_type: str
    source_family: str
    api_url: Optional[str] = None
    feed_url: Optional[str] = None
    board_url: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    headcount_bucket: Optional[str] = None
    hq_country: Optional[str] = None
    target_market_fit: str = "unknown"
    trust_score: int = 50
    enabled: bool = True
    notes: str = ""

@dataclass
class CompanyRegistryEntry:
    domain: str
    name: str
    headcount_bucket: str
    hq_country: str
    target_markets: List[str]
    company_type: str
    verified: bool
    last_verified: str

@dataclass
class JobRecord:
    company_name: str
    company_domain: str
    company_website: str
    company_headcount_bucket: str
    company_hq_country: str
    target_market_fit: str
    job_title: str
    role_family: str
    seniority: str
    location_raw: str
    remote_proof: str
    restriction_check: str
    job_url: str
    final_canonical_url: str
    posted_date: str
    days_old: int
    source_name: str
    source_family: str
    source_type: str
    source_trust_score: int
    tech_stack_detected: str
    dsi_icp_score: int
    score_reasons: str
    duplicate_key: str
    quality_tier: str = "A_STRICT_DSI_ICP"
    collected_date: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# HTTP CLIENT
# =============================================================================

class SafeHTTPClient:
    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'DSI-Elite-Collector/1.0 (+https://www.dsinnovators.com)',
            'Accept': 'text/html,application/json,*/*',
        })
        self.timeout = timeout
        self._domain_last_request: Dict[str, float] = {}
        
    def _get_domain(self, url: str) -> str:
        try:
            extracted = tldextract.extract(url)
            return f"{extracted.domain}.{extracted.suffix}"
        except:
            return urlparse(url).netloc
    
    def _wait_for_rate_limit(self, domain: str):
        now = time.time()
        last_request = self._domain_last_request.get(domain, 0)
        elapsed = now - last_request
        
        if elapsed < RATE_LIMIT_PER_DOMAIN:
            sleep_time = RATE_LIMIT_PER_DOMAIN - elapsed
            jitter = random.uniform(-JITTER_RANGE, JITTER_RANGE) * RATE_LIMIT_PER_DOMAIN
            sleep_time = max(0.1, sleep_time + jitter)
            time.sleep(sleep_time)
        
        self._domain_last_request[domain] = time.time()
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.exceptions.RequestException,)),
    )
    def fetch(self, url: str, method: str = 'GET', **kwargs) -> Optional[requests.Response]:
        domain = self._get_domain(url)
        self._wait_for_rate_limit(domain)
        
        try:
            response = self.session.request(method, url, timeout=self.timeout, allow_redirects=True, **kwargs)
            
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        time.sleep(min(int(retry_after), 60))
                    except ValueError:
                        pass
                raise requests.exceptions.RequestException("Rate limited")
            
            if response.status_code >= 400:
                logger.warning(f"HTTP {response.status_code} from {url}")
                if response.status_code in (403, 404):
                    return None
                response.raise_for_status()
            
            return response
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error fetching {url}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching {url}: {type(e).__name__}")
            return None
    
    def fetch_json(self, url: str, **kwargs) -> Optional[Dict]:
        response = self.fetch(url, **kwargs)
        if response and response.headers.get('content-type', '').startswith('application/json'):
            try:
                return response.json()
            except json.JSONDecodeError:
                pass
        return None
    
    def fetch_text(self, url: str, **kwargs) -> Optional[str]:
        response = self.fetch(url, **kwargs)
        return response.text if response else None
    
    def close(self):
        self.session.close()


# =============================================================================
# REGISTRY & CLASSIFIERS
# =============================================================================

class SourceRegistry:
    def __init__(self, sources_file: str = "sources.yml"):
        self.sources_file = sources_file
        self.sources: List[SourceDefinition] = []
        self.company_registry: Dict[str, CompanyRegistryEntry] = {}
        self._load()
    
    def _load(self):
        try:
            with open(self.sources_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            for src in data.get('sources', []):
                if src.get('enabled', True):
                    self.sources.append(SourceDefinition(**{
                        k: v for k, v in src.items() 
                        if k in SourceDefinition.__dataclass_fields__
                    }))
            
            for entry in data.get('company_registry', []):
                if entry.get('verified', False):
                    self.company_registry[entry['domain'].lower()] = CompanyRegistryEntry(**entry)
                    
            logger.info(f"Loaded {len(self.sources)} enabled sources, {len(self.company_registry)} verified companies")
            
        except FileNotFoundError:
            logger.error(f"Sources file not found: {self.sources_file}")
            sys.exit(1)
    
    def get_company_by_domain(self, domain: str) -> Optional[CompanyRegistryEntry]:
        return self.company_registry.get(domain.lower().strip('www.'))
    
    def get_company_by_name(self, name: str) -> Optional[CompanyRegistryEntry]:
        normalized = self._normalize_company_name(name)
        for entry in self.company_registry.values():
            if self._normalize_company_name(entry.name) == normalized:
                return entry
        return None
    
    def _normalize_company_name(self, name: str) -> str:
        result = name.lower()
        for pattern in COMPANY_NORMALIZE_PATTERNS:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        return result.strip()
    
    def verify_headcount(self, company_domain: str, company_name: str) -> Optional[str]:
        if company_domain:
            entry = self.get_company_by_domain(company_domain)
            if entry and entry.headcount_bucket in VALID_HEADCOUNT_BUCKETS:
                return entry.headcount_bucket
        
        if company_name:
            entry = self.get_company_by_name(company_name)
            if entry and entry.headcount_bucket in VALID_HEADCOUNT_BUCKETS:
                return entry.headcount_bucket
        
        return None

class TextClassifier:
    @staticmethod
    def has_strong_global_remote(text: str) -> bool:
        text_lower = text.lower()
        for pattern in STRONG_GLOBAL_SIGNALS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def has_weak_remote_only(text: str) -> bool:
        text_lower = text.lower()
        has_weak = any(re.search(p, text_lower, re.IGNORECASE) for p in WEAK_REMOTE_SIGNALS)
        has_strong = TextClassifier.has_strong_global_remote(text)
        return has_weak and not has_strong
    
    @staticmethod
    def has_location_restriction(text: str) -> bool:
        text_lower = text.lower()
        for pattern in LOCATION_REJECT_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def has_timezone_flexibility(text: str) -> bool:
        text_lower = text.lower()
        signals = [r'async', r'asynchronous', r'timezone.?flexible', 
                   r'any.?timezone', r'work.?any.?hours', r'flexible.?hours']
        return any(re.search(p, text_lower, re.IGNORECASE) for p in signals)
    
    @staticmethod
    def classify_role_family(title: str, description: str) -> Optional[str]:
        text = f"{title} {description}".lower()
        for pattern in REJECTED_ROLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return None
        
        for pattern, family in ROLE_FAMILY_MAP.items():
            if re.search(pattern, text, re.IGNORECASE):
                return family
        
        return None
    
    @staticmethod
    def extract_seniority(title: str) -> str:
        title_lower = title.lower()
        if re.search(r'\b(principal|staff)\b', title_lower):
            return 'senior'
        elif re.search(r'\b(lead|senior|sr\.?)\b', title_lower):
            return 'senior'
        elif re.search(r'\b(junior|jr\.?)\b', title_lower):
            return 'junior'
        return 'mid'
    
    @staticmethod
    def normalize_title(title: str) -> str:
        result = title.strip()
        for word in TITLE_NOISE_WORDS:
            result = re.sub(rf'\b{word}\b', '', result, flags=re.IGNORECASE)
        return re.sub(r'\s+', ' ', result).strip()
    
    @staticmethod
    def extract_domain(url: str) -> str:
        try:
            extracted = tldextract.extract(url)
            return f"{extracted.domain}.{extracted.suffix}".lower()
        except:
            return urlparse(url).netloc.lower()
    
    @staticmethod
    def parse_posted_date(text: str, url: str = "") -> Optional[datetime]:
        patterns = [
            r'posted[:\s]+(\w+\s+\d{1,2},?\s+\d{4})',
            r'(\w+\s+\d{1,2},?\s+\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{2}/\d{2}/\d{4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return date_parser.parse(match.group(1), fuzzy=True)
                except:
                    continue
        
        date_match = re.search(r'(\d{4})[/-](\d{2})[/-](\d{2})', url)
        if date_match:
            try:
                return datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
            except:
                pass
        
        return None

class ScoringEngine:
    @staticmethod
    def calculate(job: JobRecord, full_text: str) -> Tuple[int, List[str]]:
        score = 0
        reasons = []
        
        if TextClassifier.has_strong_global_remote(full_text):
            score += SCORING['proven_remote_worldwide']
            reasons.append("Strong global remote proof")
        
        if not TextClassifier.has_location_restriction(full_text):
            score += SCORING['no_restriction_found']
            reasons.append("No location/visa restrictions")
        
        if TextClassifier.has_timezone_flexibility(full_text):
            score += SCORING['timezone_flexible']
            reasons.append("Timezone/async friendly")
        
        if job.company_headcount_bucket in VALID_HEADCOUNT_BUCKETS:
            score += SCORING['headcount_valid']
            reasons.append(f"Headcount verified: {job.company_headcount_bucket}")
        
        if job.target_market_fit in ('high', 'medium'):
            score += SCORING['target_market_fit']
            reasons.append(f"Target market fit: {job.target_market_fit}")
        
        if job.role_family in ACCEPTED_ROLE_FAMILIES:
            score += SCORING['core_engineering_role']
            reasons.append(f"Core engineering role: {job.role_family}")
        
        if job.days_old <= 7:
            score += SCORING['fresh_0_7_days']
            reasons.append(f"Very fresh: {job.days_old} days old")
        elif job.days_old <= 14:
            score += SCORING['fresh_8_14_days']
            reasons.append(f"Fresh: {job.days_old} days old")
        elif job.days_old <= 21:
            score += SCORING['fresh_15_21_days']
            reasons.append(f"Acceptable freshness: {job.days_old} days old")
        
        if job.source_type == 'ats_api' or job.source_family in ('greenhouse', 'lever', 'ashby'):
            score += SCORING['official_ats_source']
            reasons.append("Official ATS source")
        
        if job.source_trust_score >= 75 and job.company_domain:
            score += SCORING['trusted_board_match']
            reasons.append("Trusted source with company match")
        
        if any(t in job.tech_stack_detected.lower() for t in ['saas', 'platform', 'api', 'cloud']):
            score += SCORING['product_saas_company']
            reasons.append("Product/SaaS company detected")
        
        return min(100, score), reasons

class DedupEngine:
    def __init__(self):
        self._seen_keys: Set[str] = set()
        self._seen_urls: Set[str] = set()
        self._company_roles: Dict[str, Set[str]] = {}
    
    def _generate_keys(self, job: JobRecord) -> List[str]:
        keys = []
        if job.final_canonical_url:
            keys.append(f"url:{job.final_canonical_url}")
        if job.company_domain and job.job_title:
            norm_title = TextClassifier.normalize_title(job.job_title)
            keys.append(f"company_title:{job.company_domain}:{norm_title}")
        if job.company_domain and job.role_family:
            keys.append(f"company_role:{job.company_domain}:{job.role_family}")
        if job.company_domain and job.job_title:
            fuzzy_key = f"{job.company_domain}:{TextClassifier.normalize_title(job.job_title)[:30]}"
            keys.append(f"fuzzy:{fuzzy_key}")
        return keys
    
    def is_duplicate(self, job: JobRecord) -> bool:
        keys = self._generate_keys(job)
        
        if job.final_canonical_url in self._seen_urls:
            return True
        
        for key in keys:
            if key in self._seen_keys:
                if key.startswith('fuzzy:'):
                    domain_title = key[6:]
                    domain, title_prefix = domain_title.split(':', 1)
                    if domain in self._company_roles:
                        for seen_title in self._company_roles[domain]:
                            if fuzz.ratio(title_prefix, seen_title[:30]) > 92:
                                return True
                return True
        
        if job.final_canonical_url:
            self._seen_urls.add(job.final_canonical_url)
        for key in keys:
            self._seen_keys.add(key)
        
        if job.company_domain and job.job_title:
            if job.company_domain not in self._company_roles:
                self._company_roles[job.company_domain] = set()
            self._company_roles[job.company_domain].add(
                TextClassifier.normalize_title(job.job_title)
            )
        
        return False


# =============================================================================
# MAIN SCRAPER
# =============================================================================

class DSIScraperElite:
    def __init__(self, sources_file: str = "sources.yml"):
        self.registry = SourceRegistry(sources_file)
        self.http = SafeHTTPClient()
        self.classifier = TextClassifier()
        self.scorer = ScoringEngine()
        self.dedup = DedupEngine()
        self.results: List[JobRecord] = []
        
    def _extract_company_info(self, source: SourceDefinition, job_data: Dict) -> Tuple[str, str, str]:
        if source.company_domain:
            domain = source.company_domain.lower().strip('www.')
            name = source.company_name or domain
            website = f"https://{domain}" if not domain.startswith('http') else domain
            return name, domain, website
        
        company_name = job_data.get('company_name') or job_data.get('company') or source.company_name or ""
        company_url = job_data.get('company_url') or job_data.get('application_url') or ""
        
        if company_url:
            domain = self.classifier.extract_domain(company_url)
        elif company_name:
            domain = re.sub(r'[^a-z0-9]+', '', company_name.lower()) + '.com'
        else:
            domain = self.classifier.extract_domain(job_data.get('url', ''))
        
        website = company_url if company_url.startswith('http') else f"https://{domain}"
        name = company_name or domain
        
        return name, domain, website
    
    def _fetch_greenhouse_jobs(self, source: SourceDefinition) -> List[Dict]:
        if not source.api_url or '{company}' not in source.api_url:
            return []
        
        companies_to_try = []
        if source.company_domain:
            companies_to_try.append(source.company_domain.split('.')[0])
        if source.company_name:
            companies_to_try.append(source.company_name.lower().replace(' ', '-'))
        
        for company_id in companies_to_try:
            url = source.api_url.format(company=company_id)
            data = self.http.fetch_json(url)
            if data and 'jobs' in data:
                return data['jobs']
        
        return []
    
    def _fetch_lever_jobs(self, source: SourceDefinition) -> List[Dict]:
        if not source.api_url or '{company}' not in source.api_url:
            return []
        
        company_id = source.company_domain.split('.')[0] if source.company_domain else source.company_name
        if not company_id:
            return []
        
        url = source.api_url.format(company=company_id)
        data = self.http.fetch_json(url)
        if data and isinstance(data, dict):
            return data.get('postings', [])
        return []
    
    def _fetch_board_api(self, source: SourceDefinition) -> List[Dict]:
        if not source.api_url:
            return []
        
        data = self.http.fetch_json(source.api_url)
        if not data:
            return []
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            for key in ['jobs', 'results', 'data', 'listings', 'postings']:
                if key in data and isinstance(data[key], list):
                    return data[key]
        
        return []
    
    def _fetch_rss_feed(self, source: SourceDefinition) -> List[Dict]:
        if not source.feed_url:
            return []
        
        content = self.http.fetch_text(source.feed_url)
        if not content:
            return []
        
        jobs = []
        try:
            soup = BeautifulSoup(content, 'xml')
            for item in soup.find_all('item'):
                job = {
                    'title': item.find('title').text if item.find('title') else '',
                    'url': item.find('link').text if item.find('link') else '',
                    'description': item.find('description').text if item.find('description') else '',
                    'pubDate': item.find('pubDate').text if item.find('pubDate') else '',
                }
                jobs.append(job)
        except Exception as e:
            logger.warning(f"Failed to parse RSS feed {source.feed_url}: {e}")
        
        return jobs
    
    def _process_job_data(self, source: SourceDefinition, job_data: Dict, full_text: str = "") -> Optional[JobRecord]:
        title = job_data.get('title') or job_data.get('job_title') or ""
        url = job_data.get('url') or job_data.get('apply_url') or job_data.get('job_url') or ""
        description = job_data.get('description') or job_data.get('content') or ""
        location = job_data.get('location') or job_data.get('location_name') or ""
        
        if not title or not url:
            return None
        
        full_text = full_text or f"{title} {description} {location}"
        
        company_name, company_domain, company_website = self._extract_company_info(source, job_data)
        
        headcount_bucket = self.registry.verify_headcount(company_domain, company_name)
        if not headcount_bucket:
            logger.debug(f"Rejected {title} at {company_name}: unknown headcount")
            return None
        
        role_family = self.classifier.classify_role_family(title, description)
        if not role_family:
            logger.debug(f"Rejected {title} at {company_name}: non-engineering role")
            return None
        
        if not self.classifier.has_strong_global_remote(full_text):
            logger.debug(f"Rejected {title} at {company_name}: no strong global remote proof")
            return None
        
        if self.classifier.has_location_restriction(full_text):
            logger.debug(f"Rejected {title} at {company_name}: has location restriction")
            return None
        
        posted_date = self.classifier.parse_posted_date(full_text, url)
        if not posted_date:
            pub_date = job_data.get('pubDate') or job_data.get('posted_at') or job_data.get('date_posted')
            if pub_date:
                try:
                    posted_date = date_parser.parse(pub_date, fuzzy=True)
                except:
                    pass
        
        if not posted_date:
            logger.debug(f"Rejected {title} at {company_name}: unknown posted date")
            return None
        
        days_old = (datetime.utcnow() - posted_date).days
        if days_old > MAX_JOB_AGE_DAYS:
            logger.debug(f"Rejected {title} at {company_name}: too old ({days_old} days)")
            return None
        
        target_market_fit = source.target_market_fit
        if source.company_domain and source.company_domain in self.registry.company_registry:
            reg_entry = self.registry.company_registry[source.company_domain]
            if any(tm in TARGET_MARKETS for tm in reg_entry.target_markets) or 'Global' in reg_entry.target_markets:
                target_market_fit = 'high'
        
        tech_stack = []
        tech_keywords = ['python', 'javascript', 'typescript', 'react', 'node', 'java', 
                        'golang', 'kubernetes', 'aws', 'docker', 'terraform', 'graphql']
        for tech in tech_keywords:
            if tech in full_text.lower():
                tech_stack.append(tech)
        
        provisional = JobRecord(
            company_name=company_name,
            company_domain=company_domain,
            company_website=company_website,
            company_headcount_bucket=headcount_bucket,
            company_hq_country=source.hq_country or "Unknown",
            target_market_fit=target_market_fit,
            job_title=title,
            role_family=role_family,
            seniority=self.classifier.extract_seniority(title),
            location_raw=location,
            remote_proof="strong_global" if self.classifier.has_strong_global_remote(full_text) else "weak",
            restriction_check="none_found" if not self.classifier.has_location_restriction(full_text) else "restricted",
            job_url=url,
            final_canonical_url=url,
            posted_date=posted_date.strftime("%Y-%m-%d"),
            days_old=days_old,
            source_name=source.source_name,
            source_family=source.source_family,
            source_type=source.source_type,
            source_trust_score=source.trust_score,
            tech_stack_detected=",".join(tech_stack) if tech_stack else "not_detected",
            dsi_icp_score=0,
            score_reasons="",
            duplicate_key=f"{company_domain}:{self.classifier.normalize_title(title)}"
        )
        
        score, reasons = self.scorer.calculate(provisional, full_text)
        provisional.dsi_icp_score = score
        provisional.score_reasons = "; ".join(reasons)
        
        if score < MIN_ACCEPT_SCORE:
            logger.debug(f"Rejected {title} at {company_name}: score {score} < {MIN_ACCEPT_SCORE}")
            return None
        
        return provisional
    
    def fetch_source_jobs(self, source: SourceDefinition) -> List[JobRecord]:
        jobs_found = []
        
        try:
            if source.source_family == 'greenhouse':
                raw_jobs = self._fetch_greenhouse_jobs(source)
            elif source.source_family == 'lever':
                raw_jobs = self._fetch_lever_jobs(source)
            elif source.source_type == 'board_api':
                raw_jobs = self._fetch_board_api(source)
            elif source.source_type == 'board_rss':
                raw_jobs = self._fetch_rss_feed(source)
            else:
                return []
            
            for job_data in raw_jobs:
                try:
                    full_text = ""
                    if source.source_type in ('board_api', 'board_rss') and job_data.get('url'):
                        detail = self.http.fetch_text(job_data['url'])
                        if detail:
                            soup = BeautifulSoup(detail, 'html.parser')
                            for tag in soup(['script', 'style']):
                                tag.decompose()
                            full_text = soup.get_text(separator=' ', strip=True)
                    
                    job_record = self._process_job_data(source, job_data, full_text)
                    if job_record and not self.dedup.is_duplicate(job_record):
                        jobs_found.append(job_record)
                        
                except Exception as e:
                    logger.debug(f"Error processing job from {source.source_name}: {e}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Error fetching source {source.source_name}: {e}")
        
        return jobs_found
    
    def run(self, output_dir: str = ".") -> str:
        # --- FIX: Automatically create the directory if it doesn't exist ---
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info("Starting DSI Elite collection run")
        
        total_sources = len(self.registry.sources)
        logger.info(f"Processing {total_sources} enabled sources")
        
        for i, source in enumerate(self.registry.sources, 1):
            logger.info(f"[{i}/{total_sources}] Fetching: {source.source_name}")
            
            try:
                jobs = self.fetch_source_jobs(source)
                self.results.extend(jobs)
                logger.info(f"  -> Found {len(jobs)} qualified jobs")
            except Exception as e:
                logger.warning(f"Error with source {source.source_name}: {e}")
                continue
        
        date_str = datetime.utcnow().strftime("%Y_%m_%d")
        output_file = os.path.join(output_dir, f"FINAL_USE_THIS_ONLY_{date_str}.csv")
        
        columns = [
            'quality_tier', 'company_name', 'company_domain', 'company_website',
            'company_headcount_bucket', 'company_hq_country', 'target_market_fit',
            'job_title', 'role_family', 'seniority', 'location_raw', 'remote_proof',
            'restriction_check', 'job_url', 'final_canonical_url', 'posted_date',
            'days_old', 'source_name', 'source_family', 'source_type',
            'source_trust_score', 'tech_stack_detected', 'dsi_icp_score',
            'score_reasons', 'duplicate_key', 'collected_date'
        ]
        
        if self.results:
            df = pd.DataFrame([r.to_dict() for r in self.results])
            df = df[columns]
            df.to_csv(output_file, index=False)
            logger.info(f"✅ Wrote {len(self.results)} rows to {output_file}")
        else:
            df = pd.DataFrame(columns=columns)
            df.to_csv(output_file, index=False)
            logger.info("⚠️  No strict ICP rows found. Do not use weak data. Add more verified company sources.")
        
        if len(self.results) < 500:
            logger.info(f"Strict quality found {len(self.results)} rows. To scale, add more verified 10 to 200 headcount remote first companies to sources.yml.")
        
        self.http.close()
        
        return output_file


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='DSI Innovators Elite Job Collector')
    parser.add_argument('--output-dir', '-o', default='.', help='Output directory for CSV')
    parser.add_argument('--sources', '-s', default='sources.yml', help='Path to sources.yml')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    scraper = DSIScraperElite(sources_file=args.sources)
    output_path = scraper.run(output_dir=args.output_dir)
    
    print(f"\n📊 Collection complete: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
