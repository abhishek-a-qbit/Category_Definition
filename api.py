"""
FastAPI application for Category Definition workflow
Based on test.ipynb - searches, scrapes, scores, and synthesizes category definitions
"""

import os
import re
import hashlib
import json
import pathlib
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import trafilatura
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# Load environment variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env")
if not SERPER_API_KEY:
    raise ValueError("SERPER_API_KEY not found in .env")

# Initialize FastAPI app
app = FastAPI(title="Category Definition API", version="1.0.0")

# Cache directory
CACHE_DIR = pathlib.Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

# Configuration constants
SEARCH_DELAY = 0.3
SCRAPE_DELAY = 0.5
LLM_DELAY = 0.2
SYNTHESIS_TOP_N = 20
SYNTHESIS_CONTENT_CHARS = 3000

# Category configuration
TEST_CATEGORY = "Account-Based Marketing"
CATEGORY_MATURITY = "evolving"
CATEGORY_ALIASES = [
    "Account-Based Marketing",
    "ABM",
    "Account-Based Marketing Platforms",
    "ABM platforms",
    "Account-Based Everything",
    "ABX",
    "Account-Based Experience",
]

# Trusted sites by tier
TIER1_SITES = [
    "blogs.gartner.com",
    "gartner.com/en/articles",
    "gartner.com/en/marketing/glossary",
    "gartner.com/en/information-technology/glossary",
    "gartner.com/en/sales/glossary",
    "forrester.com",
    "go.forrester.com",
    "idc.com",
    "blogs.idc.com",
]

TIER2_SITES = [
    "constellationr.com",
    "isg-one.com",
    "gigaom.com",
    "nucleusresearch.com",
    "aragonresearch.com",
]

KEY_TIER2_SITES = [
    "constellationr.com",
    "isg-one.com",
    "gigaom.com",
    "nucleusresearch.com",
    "aragonresearch.com",
]

DROP_URL_PATTERNS = [
    "/software-reviews/",
    "/compare/",
    "/products/",
    "gpivendorresources",
    "gartner.com/reviews",
    "gartner.com/en/digital-markets",
    "g2.com", "trustradius.com", "capterra.com", "getapp.com",
    "sourceforge.net", "goodfirms.co", "crozdesk.com",
    "/sponsors/",
    "/event/",
]

SERPER_EXCLUDE_SITES = [
    "store.frost.com", "my.idc.com", "info.idc.com", "view.frost.com",
    "hub.frost.com", "web-assets.bcg.com", "keithdawson.isg-one.com",
    "portal.gigaom.com", "linkedin.com", "youtube.com", "wikipedia.org",
    "optimizely.com", "salesforce.com", "adobe.com", "oracle.com",
    "demandbase.com", "cognism.com", "zoomforth.com", "factors.ai",
    "influ2.com", "mutinyhq.com", "marketone.com", "strategicabm.com",
    "clay.com", "hginsights.com", "xgrowth.com.au", "datalane.com",
]

SERPER_EXCLUDE_INURL = [
    "/wp-content/uploads/", "/content/dam/", "/docs/default-source/",
    "/downloads/", "event-pdf-generator",
]

_exc_parts = ["-filetype:pdf"]
_exc_parts += [f"-site:{s}" for s in SERPER_EXCLUDE_SITES]
_exc_parts += [f'-inurl:"{p}"' for p in SERPER_EXCLUDE_INURL]
SERPER_EXCLUSIONS = " ".join(_exc_parts)

CURRENCY_THRESHOLDS = {"emerging": 12, "evolving": 24, "stable": 36}
MAX_SOURCE_AGE_MONTHS = CURRENCY_THRESHOLDS[CATEGORY_MATURITY]

FOCUSED_ALIASES = [
    "Account-Based Marketing",
    "ABM platforms",
]

SECONDARY_ALIASES = [
    "Account-Based Marketing Platforms",
    "Account-Based Everything",
]

# Pydantic models for API
class CategoryConfig(BaseModel):
    category: str = TEST_CATEGORY
    maturity: str = CATEGORY_MATURITY
    aliases: List[str] = CATEGORY_ALIASES
    max_source_age_months: int = MAX_SOURCE_AGE_MONTHS

class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str
    query_alias: str
    search_pass: str

class ScrapedSource(BaseModel):
    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    text: str
    hostname: Optional[str] = None
    query_alias: str
    search_pass: str

class SourceScore(BaseModel):
    slot_definition: bool
    slot_capabilities: bool
    slot_boundaries: bool
    slot_buyer_use: bool
    slot_vendors: bool
    slots_filled: int
    uses_function_verbs: bool
    vendor_count: int
    vendor_names: List[str]
    is_sme_content: bool
    byline_quality: str
    single_vendor_bias: bool
    relevance_score: int
    reasoning: str

class CategoryPage(BaseModel):
    category_name: str
    aliases: List[str]
    definition: str
    core_capabilities: List[str]
    boundaries: str
    buyer_use_case: str
    representative_vendors: List[str]
    category_drift: str
    market_overview: str
    implementation_considerations: str
    vendor_landscape: str
    future_trends: str
    integration_points: str
    success_metrics: str
    common_challenges: str
    source_count: int
    confidence: str

# Cache functions
def _cache_key(*parts) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()

def cache_get(namespace: str, *key_parts):
    h = _cache_key(*key_parts)
    p = CACHE_DIR / namespace / f"{h}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None

def cache_set(namespace: str, value, *key_parts):
    h = _cache_key(*key_parts)
    d = CACHE_DIR / namespace
    d.mkdir(exist_ok=True)
    p = d / f"{h}.json"
    p.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")

def cache_stats():
    stats = {}
    if CACHE_DIR.exists():
        for ns in sorted(CACHE_DIR.iterdir()):
            if ns.is_dir():
                files = list(ns.glob("*.json"))
                stats[ns.name] = len(files)
    return stats

# Helper functions
def source_age_months(date_str: str) -> Optional[int]:
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        delta = datetime.now() - dt
        return int(delta.days / 30.44)
    except (ValueError, TypeError):
        return None


def build_serper_date_filter(max_age_months: int) -> str:
    if not max_age_months or max_age_months <= 0:
        return ""
    cutoff = datetime.now() - timedelta(days=int(max_age_months * 30.44))
    return f"after:{cutoff.strftime('%Y-%m-%d')}"


def serper_search(query: str, api_key: str, num: int = 10, **kwargs) -> List[Dict]:
    cached = cache_get("serper", query, num, kwargs)
    if cached is not None:
        return cached
    payload = {"q": query, "num": num}
    payload.update(kwargs)
    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("organic", [])
    cache_set("serper", results, query, num, kwargs)
    time.sleep(SEARCH_DELAY)
    return results

def batch_site_queries(sites: List[str], batch_size: int = 5) -> List[str]:
    batches = []
    for i in range(0, len(sites), batch_size):
        chunk = sites[i : i + batch_size]
        clause = " OR ".join(f"site:{s}" for s in chunk)
        batches.append(f"({clause})")
    return batches

def url_is_blocked(url: str) -> bool:
    url_lower = url.lower()
    for pattern in DROP_URL_PATTERNS:
        if pattern in url_lower:
            return True
    return False

def url_is_from_allowed_sites(url: str, allowed_sites: List[str]) -> bool:
    hostname = urlparse(url).netloc.lower()
    for allowed in allowed_sites:
        allowed_lower = allowed.lower()
        if hostname == allowed_lower or hostname.endswith('.' + allowed_lower):
            return True
    return False

def extract_article(url: str) -> Optional[Dict]:
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {"_error": "fetch returned empty (403/timeout/JS-only)"}
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            output_format="txt",
        )
        if not text:
            return {"_error": "extraction returned no text (template page?)"}
        meta = trafilatura.metadata.extract_metadata(downloaded)
        return {
            "url": url,
            "title": meta.title if meta else "",
            "author": meta.author if meta else "",
            "date": meta.date if meta else "",
            "text": text,
            "hostname": meta.sitename if meta else "",
        }
    except Exception as e:
        return {"_error": f"exception: {type(e).__name__}: {e}"}

NON_CONTENT_URL_PATTERNS = [
    "/page/", "/tag/", "/author/", "/hub/",
    "/search", "/login", "/register", "/contact",
    "/privacy", "/terms", "/about", "/careers",
    "/events", "/webinars", "/podcasts", "/videos",
    "/download", "/pdf", "/whitepaper", "/ebook",
    "/trial", "/demo", "/pricing", "/buy",
    "/cart", "/checkout", "/payment", "/subscribe",
]

VENDOR_TITLE_PATTERNS = [
    "best", "top", "vs", "comparison", "review", "rating",
    "pricing", "cost", "trial", "demo", "free",
    "buy now", "get started", "sign up", "download",
]

# Post-scrape: only reject broken/empty fetches. Semantic quality is handled by LLM scoring.
MIN_SCRAPED_TEXT_LEN = 100  # Reduced to 100 chars to capture concise expert content (e.g., analyst blog posts)
MIN_TITLE_LEN = 10




def should_scrape_url(url: str, title: str, search_pass: str) -> Tuple[bool, str]:
    """Pre-scrape filter: decide if URL should be scraped (restored from e905990 / test.ipynb)."""
    url_lower = url.lower()
    for pattern in DROP_URL_PATTERNS:
        if pattern in url_lower:
            return False, f"DROP_URL_PATTERN: {pattern}"

    hostname = urlparse(url).netloc.lower()
    for blocked in SERPER_EXCLUDE_SITES:
        if blocked in hostname:
            return False, f"BLOCKED_DOMAIN: {blocked}"

    for pattern in NON_CONTENT_URL_PATTERNS:
        if pattern in url_lower:
            return False, f"NON_CONTENT_PATTERN: {pattern}"

    if not title or len(title.strip()) < MIN_TITLE_LEN:
        return False, "SHORT_OR_MISSING_TITLE"

    title_lower = title.lower()
    for pattern in VENDOR_TITLE_PATTERNS:
        if pattern in title_lower and len(title_lower.split()) < 8:
            return False, f"VENDOR_TITLE_PATTERN: {pattern}"

    if search_pass.startswith("Tier2"):
        if not any(ind in url_lower for ind in ("blog", "article", "research", "insight", "analysis", "report")):
            return False, "TIER2_NON_CONTENT_URL"

    return True, "PASS"


def should_keep_scraped_content(article: Dict, max_age_months: int) -> Tuple[bool, str]:
    """
    Post-scrape gate: drop pages that failed to fetch, have no usable text, or are too old.

    Age is enforced here strictly because search filters are best-effort and may miss older results.
    """
    if not article or "_error" in article:
        return False, f"SCRAPE_ERROR: {article.get('_error', 'unknown')}"

    text = article.get("text", "")
    if not text or len(text.strip()) < MIN_SCRAPED_TEXT_LEN:
        return False, f"TOO_SHORT: {len(text)} chars"

    age = source_age_months(article.get("date"))
    if age is None:
        return False, "UNKNOWN_DATE"
    if age >= max_age_months:
        return False, f"TOO_OLD: {age} months"

    return True, "PASS"


_PLACEHOLDER_VENDOR = re.compile(r"^vendor\s*\d+$", re.I)
# Ad/social channels and generic labels — not category software vendors
_EXCLUDED_VENDOR_TERMS = frozenset({
    "programmatic display", "display advertising", "social media", "social",
    "linkedin", "meta", "facebook", "tiktok", "reddit", "google", "twitter",
    "youtube", "email", "crm", "erp", "analytics", "advertising",
})
_GENERIC_VENDOR_PHRASES = (
    "marketing technology",
    "marketing automation",
    "customer data platform",
    "customer data platforms",
    "cdp",
    "demand generation",
    "sales enablement",
    "intent data",
    "account intelligence",
    "buyer intent",
    "pipeline management",
    "demand orchestration",
    "account-based experience",
    "account-based everything",
    "b2b marketing",
    "account-based marketing platform",
    "abm platform",
    "marketing orchestration",
    "analytics platform",
    "marketing analytics",
    "account-based marketing",
    "lead generation",
    "lead scoring",
    "customer experience",
    "customer engagement",
    "revenue operations",
    "predictive analytics",
    "sales and marketing alignment",
    "target account",
    "account engagement",
    "demand gen",
)
_GENERIC_VENDOR_TOKENS = frozenset({
    "platform", "software", "solution", "service", "services",
    "technology", "technologies", "automation", "analytics", "management",
    "system", "systems", "stack", "suite", "engine", "tool", "tools",
})


def is_generic_vendor_label(name: str) -> bool:
    lower = name.lower().strip()
    if not lower:
        return True
    if lower in _EXCLUDED_VENDOR_TERMS:
        return True
    if any(phrase in lower for phrase in _GENERIC_VENDOR_PHRASES):
        return True
    if any(token in lower for token in _GENERIC_VENDOR_TOKENS) and any(
        cat in lower for cat in (
            "marketing", "account-based", "b2b", "demand", "intent",
            "sales", "customer", "analytics", "data", "campaign",
            "orchestration", "experience", "platform",
        )
    ):
        return True
    return False


def sanitize_vendor_names(names: List[str]) -> List[str]:
    """Drop placeholders and non-vendor labels from scored vendor lists."""
    out: List[str] = []
    for raw in names or []:
        name = (raw or "").strip()
        if not name or len(name) < 2:
            continue
        if _PLACEHOLDER_VENDOR.match(name):
            continue
        if is_generic_vendor_label(name):
            continue
        out.append(name)
    seen: set = set()
    deduped: List[str] = []
    for n in out:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(n)
    return deduped


def aggregate_category_vendors(synthesis_sources: List[Dict]) -> List[str]:
    """Union of category vendors from synthesis sources, ranked by mention frequency."""
    counts: Dict[str, int] = {}
    canonical: Dict[str, str] = {}
    for item in synthesis_sources:
        for v in sanitize_vendor_names(item.get("score", {}).get("vendor_names", [])):
            key = v.lower()
            counts[key] = counts.get(key, 0) + 1
            canonical.setdefault(key, v)
    return [canonical[k] for k in sorted(counts.keys(), key=lambda x: (-counts[x], x))]


def _vendor_name_from_synthesis_entry(entry: str) -> str:
    return entry.split("(")[0].split("—")[0].split(" - ")[0].strip()


def _vendor_matches_allowed(name: str, allowed: List[str]) -> bool:
    nl = name.lower()
    for a in allowed:
        al = a.lower()
        if nl == al or nl.startswith(al + " ") or al in nl:
            return True
    return False


def apply_authoritative_vendors_to_synthesis(
    synthesis_out: Dict,
    allowed_vendors: List[str],
    category: str,
) -> Dict:
    """Ensure representative_vendors only lists vendors grounded in source scores."""
    if not allowed_vendors:
        return synthesis_out
    rep = synthesis_out.get("representative_vendors") or []
    kept = [
        entry for entry in rep
        if _vendor_matches_allowed(_vendor_name_from_synthesis_entry(entry), allowed_vendors)
    ]
    if not kept:
        kept = [
            f"{v} — representative {category} vendor cited in analyst sources"
            for v in allowed_vendors[:20]
        ]
    synthesis_out["representative_vendors"] = kept
    return synthesis_out


def normalize_scored_vendor_fields(score_dict: Dict) -> Dict:
    names = sanitize_vendor_names(score_dict.get("vendor_names", []))
    score_dict["vendor_names"] = names
    score_dict["vendor_count"] = len(names)
    score_dict["slot_vendors"] = len(names) > 0
    return score_dict


def select_sources_for_synthesis(scored_sources: List[Dict]) -> List[Dict]:
    """Pick up to SYNTHESIS_TOP_N sources for synthesis (same rules as /synthesize)."""
    qualified = [
        item for item in scored_sources
        if item["score"]["relevance_score"] >= 3
        and item["score"]["slots_filled"] >= 1
        and not item["score"]["single_vendor_bias"]
    ]
    if len(qualified) < 3:
        qualified = [
            item for item in scored_sources
            if item["score"]["relevance_score"] >= 3
            and item["score"]["slots_filled"] >= 1
        ]
    return qualified[:SYNTHESIS_TOP_N]


def format_synthesis_source_links(synthesis_sources: List[Dict]) -> List[Dict]:
    """Serializable link rows for UI and exports."""
    links = []
    for item in synthesis_sources:
        s = item.get("source", {})
        sc = item.get("score", {})
        url = s.get("url") or ""
        if not url:
            continue
        links.append({
            "url": url,
            "title": s.get("title") or "Untitled",
            "author": s.get("author") or "",
            "hostname": s.get("hostname") or "",
            "search_pass": s.get("search_pass") or "",
            "query_alias": s.get("query_alias") or "",
            "relevance_score": sc.get("relevance_score"),
            "slots_filled": sc.get("slots_filled"),
        })
    return links


def _evaluate_pre_scrape_cases(cases: List[Dict], expected_reject: bool) -> Dict:
    rows = []
    for case in cases:
        keep, reason = should_scrape_url(case["url"], case["title"], case["search_pass"])
        rejected = not keep
        rows.append({
            "url": case["url"],
            "title": case["title"][:80],
            "expected": "reject" if expected_reject else "keep",
            "actual": "reject" if rejected else "keep",
            "reason": reason,
            "pass": rejected == expected_reject,
        })
    passed = sum(1 for r in rows if r["pass"])
    return {
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": round(passed / len(rows), 3) if rows else 1.0,
        "cases": rows,
    }


def _evaluate_post_scrape_cases(cases: List[Dict], expected_reject: bool) -> Dict:
    rows = []
    for case in cases:
        keep, reason = should_keep_scraped_content(case, MAX_SOURCE_AGE_MONTHS)
        rejected = not keep
        rows.append({
            "url": case.get("url", ""),
            "title": (case.get("title") or "")[:80],
            "expected": "reject" if expected_reject else "keep",
            "actual": "reject" if rejected else "keep",
            "reason": reason,
            "pass": rejected == expected_reject,
        })
    passed = sum(1 for r in rows if r["pass"])
    return {
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": round(passed / len(rows), 3) if rows else 1.0,
        "cases": rows,
    }




# API Endpoints
@app.get("/")
async def root():
    return {"message": "Category Definition API", "version": "1.0.0"}

@app.get("/config")
async def get_config():
    """Get current category configuration"""
    config = CategoryConfig()
    return {
        "category": config.category,
        "maturity": config.maturity,
        "aliases": config.aliases,
        "max_source_age_months": config.max_source_age_months,
        "focused_aliases": FOCUSED_ALIASES,
        "secondary_aliases": SECONDARY_ALIASES
    }

@app.post("/config")
async def update_config(config: CategoryConfig):
    """Update category configuration"""
    global TEST_CATEGORY, CATEGORY_MATURITY, CATEGORY_ALIASES, MAX_SOURCE_AGE_MONTHS, FOCUSED_ALIASES, SECONDARY_ALIASES
    TEST_CATEGORY = config.category
    CATEGORY_MATURITY = config.maturity
    CATEGORY_ALIASES = config.aliases
    MAX_SOURCE_AGE_MONTHS = config.max_source_age_months
    
    # Split aliases into focused (first 2) and secondary (remaining)
    if len(CATEGORY_ALIASES) >= 2:
        FOCUSED_ALIASES = CATEGORY_ALIASES[:2]
        SECONDARY_ALIASES = CATEGORY_ALIASES[2:]
    elif len(CATEGORY_ALIASES) == 1:
        FOCUSED_ALIASES = CATEGORY_ALIASES
        SECONDARY_ALIASES = []
    else:
        FOCUSED_ALIASES = []
        SECONDARY_ALIASES = []
    
    return {"message": "Configuration updated", "config": config}

@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    stats = {}
    for namespace in os.listdir(CACHE_DIR):
        namespace_path = os.path.join(CACHE_DIR, namespace)
        if os.path.isdir(namespace_path):
            stats[namespace] = len([f for f in os.listdir(namespace_path) if f.endswith('.json')])
    return stats

@app.delete("/cache")
async def clear_cache(namespace: str = None):
    """Clear cache - optionally clear only specific namespace"""
    import shutil
    if namespace:
        # Clear only specific namespace
        namespace_path = os.path.join(CACHE_DIR, namespace)
        if os.path.exists(namespace_path):
            shutil.rmtree(namespace_path)
            os.makedirs(namespace_path)
        return {"message": f"Cache cleared for namespace: {namespace}"}
    else:
        # Clear all cache
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
            os.makedirs(CACHE_DIR)
        return {"message": "All cache cleared"}

@app.post("/search")
async def search_sources():
    """Step 1: Search for sources using Serper"""
    seen_urls = set()
    all_results = []
    total_queries = 0
    total_blocked = 0
    
    # Pass 1: Tier 1 primary aliases
    def run_search_pass(name: str, sites: List[str], aliases: List[str], batch_size: int, num_per_query: int = 10):
        nonlocal total_queries
        batches = batch_site_queries(sites, batch_size=batch_size)
        queries_run = 0
        hits_added = 0
        blocked = 0
        
        date_filter = build_serper_date_filter(MAX_SOURCE_AGE_MONTHS)
        for alias in aliases:
            for site_clause in batches:
                query = f'{site_clause} "{alias}" {date_filter} {SERPER_EXCLUSIONS}'.strip()
                queries_run += 1
                
                try:
                    hits = serper_search(query, SERPER_API_KEY, num=num_per_query)
                    
                    for h in hits:
                        url = h.get("link", "")
                        if not url or url in seen_urls:
                            continue
                        
                        if not url_is_from_allowed_sites(url, sites):
                            blocked += 1
                            continue
                        
                        if url_is_blocked(url):
                            blocked += 1
                            continue
                        
                        seen_urls.add(url)
                        all_results.append({
                            "url": url,
                            "title": h.get("title", ""),
                            "snippet": h.get("snippet", ""),
                            "query_alias": alias,
                            "search_pass": name,
                        })
                        hits_added += 1
                        
                except Exception as e:
                    pass
        
        total_queries += queries_run
        return {"queries_run": queries_run, "hits_added": hits_added, "blocked": blocked}

    pass_stats = []
    pass_stats.append(run_search_pass("Tier1-primary", TIER1_SITES, FOCUSED_ALIASES, batch_size=3))
    pass_stats.append(run_search_pass("Tier1-secondary", TIER1_SITES, SECONDARY_ALIASES, batch_size=3))
    pass_stats.append(run_search_pass("Tier2-key", KEY_TIER2_SITES, FOCUSED_ALIASES, batch_size=5))
    pass_stats.append(run_search_pass("Tier2-key", KEY_TIER2_SITES, SECONDARY_ALIASES, batch_size=5))
    total_blocked = sum(s["blocked"] for s in pass_stats)
    
    return {
        "total_queries": total_queries,
        "total_urls": len(all_results),
        "search_blocked_at_search": total_blocked,
        "results": all_results,
        
        "note": (
            "search_blocked_at_search uses DROP_URL_PATTERNS only. "
            "Search queries also include a date filter to restrict results to sources younger than the configured max source age. "
            "There is no pre-scrape filtering in the current workflow. "
            "Post-scrape keeps all successful fetches with >=100 chars for scoring."
        ),
    }

@app.post("/scrape")
async def scrape_sources(search_results: List[SearchResult]):
    """Step 2: Scrape content from search results"""
    scraped_sources = []
    scrape_failures = []
    
    for result in search_results:
        article = extract_article(result.url)
        
        should_keep, keep_reason = should_keep_scraped_content(article, MAX_SOURCE_AGE_MONTHS)
        
        if should_keep:
            article["query_alias"] = result.query_alias
            article["search_pass"] = result.search_pass
            scraped_sources.append(article)
        else:
            scrape_failures.append({
                "url": result.url,
                "reason": keep_reason
            })
        
        time.sleep(SCRAPE_DELAY)

    post_scrape_breakdown: Dict[str, int] = {}
    for item in scrape_failures:
        key = item["reason"].split(":")[0]
        post_scrape_breakdown[key] = post_scrape_breakdown.get(key, 0) + 1

    return {
        "original_count": len(search_results),
        "attempted_scrape": len(search_results),
        "successfully_scraped": len(scraped_sources),
        "post_scrape_filtered": len(scrape_failures),
        "post_scrape_breakdown": post_scrape_breakdown,
        "scraped_sources": scraped_sources,
        "scrape_failures": scrape_failures[:10]
    }


@app.post("/validate-filters")
async def validate_filters_endpoint():
    """Run labeled pre/post filter comparison without scraping."""
    return validate_scrape_filters()

@app.post("/deduplicate")
async def deduplicate_sources(scraped_sources: List[ScrapedSource]):
    """Step 3: Deduplicate near-identical content"""
    def _content_hash(text: str) -> str:
        return hashlib.md5(text[:500].strip().lower().encode()).hexdigest()
    
    _seen_hashes = set()
    deduped_sources = []
    dupes_removed = 0
    
    for s in scraped_sources:
        h = _content_hash(s.text)
        if h in _seen_hashes:
            dupes_removed += 1
            continue
        _seen_hashes.add(h)
        deduped_sources.append(s)
    
    return {
        "before_count": len(scraped_sources),
        "duplicates_removed": dupes_removed,
        "after_count": len(deduped_sources),
        "deduped_sources": [s.model_dump() for s in deduped_sources],
    }

@app.post("/score")
async def score_sources(sources: List[ScrapedSource]):
    """Step 4: Score sources using LLM"""
    from pydantic import BaseModel, Field
    
    class SourceScoreModel(BaseModel):
        slot_definition: bool = Field(description="Contains a category definition")
        slot_capabilities: bool = Field(description="Lists core capabilities of the software")
        slot_boundaries: bool = Field(description="Distinguishes from adjacent/related categories")
        slot_buyer_use: bool = Field(description="Describes buyer persona or use case")
        slot_vendors: bool = Field(description="Names representative vendors/products")
        slots_filled: int = Field(description="Count of slots filled (0-5)")
        uses_function_verbs: bool = Field(description="Uses expert verbs like orchestrate, unify, score, route, match")
        vendor_count: int = Field(description="Number of distinct vendors/products mentioned")
        vendor_names: list[str] = Field(description="List of distinct vendor/product names found")
        is_sme_content: bool = Field(description="Appears to be written by or for subject-matter experts")
        byline_quality: str = Field(description="'named_analyst' if byline is a recognized analyst, 'named_author' if any named author, 'no_byline' if anonymous")
        single_vendor_bias: bool = Field(description="True if source primarily promotes a single vendor")
        relevance_score: int = Field(description="1-10 overall relevance to defining the software category")
        reasoning: str = Field(description="Brief explanation of the score")
    
    SCORING_PROMPT = ChatPromptTemplate.from_messages([
        ("system", """You are evaluating a web source for its usefulness in defining the software category "{category}".

**IMPORTANT**: Expert analyst content is often CONCISE. Brief, high-quality expert writing is superior to lengthy marketing fluff. Do NOT penalize sources for brevity.

CRITICAL FIRST CHECK: Determine whether the scraped content MAINLY talks about the category "{category}".
- Read the full content carefully. Is the primary subject matter actually about "{category}"?
- If the content is about a different topic, a different software category, or only mentions "{category}" tangentially, it is NOT relevant.
- If the content does NOT mainly discuss "{category}", you MUST set relevance_score to 0-2 (low) and explain in reasoning why it's not relevant.

After the category relevance check, score on these criteria:
1. SLOT-FILL: Does it contain (a) a definition, (b) core capabilities, (c) boundaries vs adjacent categories, (d) buyer/use case, (e) representative vendors? Count how many of these 5 slots it fills. A brief but clear explanation of each slot is valuable; length does not determine slot quality.
2. FUNCTION-VERBS: Does it use expert verbs (orchestrate, unify, score, route, match, segment, personalize, align) rather than SEO adjectives?
3. BYLINE QUALITY: Evaluate the author byline - "named_analyst", "named_author", or "no_byline".
4. CATEGORY VENDORS: Extract ONLY companies that sell software/platforms in the "{category}" category (named in the article as vendors/products in THAT category). Use exact company names from the text. Do NOT return generic categories, product types, software labels, or non-vendor descriptions such as "marketing automation", "customer data platform", "ABM platform", "account-based experience", "demand orchestration", "analytics platform", or "lead management solution". EXCLUDE: placeholders (Vendor 1, Vendor 2), social/ad channels (LinkedIn, Meta, TikTok, Reddit, Google), generic labels (programmatic display), and vendors from adjacent categories (CRM, ERP, MAP) unless the article explicitly lists them as "{category}" platform vendors. If none are named for this category, return vendor_names: [] and vendor_count: 0.
5. SME CONTENT: Is this analyst/expert content or marketing fluff? Analyst blogs and concise expert commentary = SME content. Marketing-heavy product comparison pages = not SME.
6. RELEVANCE: How useful is this {category} source (1-10)? Score based on RELEVANCE and SLOT-FILL quality, NOT content length. A 2-paragraph expert source with 3-4 slots filled should score 7-9, not 2-3. A 50-paragraph marketing page with 1 slot should score 3-4.

Return valid JSON matching the schema."""),
        ("human", """Source URL: {url}
Title: {title}
Author: {author}
Date: {date}
Host: {hostname}
Source age: {source_age}

Content (first 3000 chars):
{text}"""),
    ])
    
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    structured_llm = llm.with_structured_output(SourceScoreModel)
    chain = SCORING_PROMPT | structured_llm
    
    scored_sources = []
    cache_hits = 0
    skipped_due_to_age = 0
    skipped_unknown_date = 0
    filtered_sources = []

    for s in sources:
        age = source_age_months(s.date)
        if age is None:
            skipped_unknown_date += 1
            continue
        if age >= MAX_SOURCE_AGE_MONTHS:
            skipped_due_to_age += 1
            continue
        filtered_sources.append(s)

    for i, s in enumerate(filtered_sources):
        text_trunc = s.text[:3000]
        age = source_age_months(s.date)
        age_str = f"{age} months" if age is not None else "unknown"
        
        invoke_params = {
            "category": TEST_CATEGORY,
            "url": s.url,
            "title": s.title or "Unknown",
            "author": s.author or "Unknown",
            "date": s.date or "Unknown",
            "hostname": s.hostname or "Unknown",
            "source_age": age_str,
            "text": text_trunc,
        }
        
        cache_key_parts = ("scoring_v3_category_vendors", TEST_CATEGORY, s.url, s.title or "Unknown",
                           s.author or "Unknown", s.date or "Unknown",
                           s.hostname or "Unknown", text_trunc)
        cached = cache_get("llm_scoring", *cache_key_parts)
        
        if cached is not None:
            score_data = cached["score"] if "score" in cached else cached
            score_data = normalize_scored_vendor_fields(dict(score_data))
            cache_hits += 1
            scored_sources.append({"source": s.model_dump(), "score": score_data})
            continue
        
        try:
            score = chain.invoke(invoke_params)
            score_data = normalize_scored_vendor_fields(score.model_dump())
            rendered_msgs = SCORING_PROMPT.format_messages(**invoke_params)
            rendered_prompt = "\n".join(f"[{m.type}] {m.content}" for m in rendered_msgs)
            cache_set("llm_scoring", {
                "score": score_data,
                "prompt": rendered_prompt,
            }, *cache_key_parts)
            scored_sources.append({"source": s.model_dump(), "score": score_data})
            time.sleep(LLM_DELAY)
        except Exception as e:
            pass
    
    # Sort by relevance score descending
    scored_sources.sort(key=lambda x: x["score"]["relevance_score"], reverse=True)
    
    return {
        "total_scored": len(scored_sources),
        "cache_hits": cache_hits,
        "new_llm_calls": len(scored_sources) - cache_hits,
        "skipped_due_to_age": skipped_due_to_age,
        "skipped_unknown_date": skipped_unknown_date,
        "scored_sources": scored_sources,
    }

@app.post("/synthesize")
async def synthesize_category(scored_sources: List[Dict]):
    """Step 5: Synthesize comprehensive category page from top sources"""
    from pydantic import BaseModel, Field
    
    class CategoryPageModel(BaseModel):
        category_name: str = Field(description="Primary category name")
        aliases: list[str] = Field(description="Known aliases for this category")
        definition: str = Field(description="2-4 sentence category definition")
        core_capabilities: list[str] = Field(description="Detailed core software capabilities")
        boundaries: str = Field(description="Explanation of what this category is NOT")
        buyer_use_case: str = Field(description="Description of buyer personas and use cases")
        representative_vendors: list[str] = Field(
            description="ONLY vendors from the authoritative category vendor list provided in the prompt; one entry per vendor with brief positioning"
        )
        category_drift: str = Field(description="Analysis of analyst disagreement")
        market_overview: str = Field(description="Market size, growth trends")
        implementation_considerations: str = Field(description="Key implementation considerations")
        vendor_landscape: str = Field(description="Analysis of vendor ecosystem")
        future_trends: str = Field(description="Emerging trends and future direction")
        integration_points: str = Field(description="Integration with other systems")
        success_metrics: str = Field(description="Key metrics and KPIs")
        common_challenges: str = Field(description="Typical challenges")
        source_count: int = Field(description="Number of sources used")
        confidence: str = Field(description="high/medium/low")
    
    synthesis_sources = select_sources_for_synthesis(scored_sources)
    synthesis_source_links = format_synthesis_source_links(synthesis_sources)
    category_vendors = aggregate_category_vendors(synthesis_sources)
    vendors_block = (
        ", ".join(category_vendors)
        if category_vendors
        else "(none extracted from sources — leave representative_vendors empty)"
    )

    source_summaries = []
    for item in synthesis_sources:
        s = item["source"]
        sc = item["score"]
        source_summaries.append(f"""
Source: {s['title']}
Author: {s['author']}
URL: {s['url']}
Relevance: {sc['relevance_score']}/10
Slots filled: {sc['slots_filled']}/5
Vendors: {', '.join(sc['vendor_names'])}
Content: {s['text'][:SYNTHESIS_CONTENT_CHARS]}...
---""")
    
    sources_text = "\n".join(source_summaries)
    
    COMPREHENSIVE_SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages([
        ("system", """You are writing an extremely comprehensive category definition page that reads like a definitive industry report. The page must be written in editorial voice — no direct quotation from sources. Multi-source consensus carries definition.

IMPORTANT GROUNDING RULES:
- Use ONLY the facts and details found in the provided source content.
- Do NOT invent any information, statistics, vendor names, capabilities, use cases, or market analysis that is not directly supported by the source content.
- Do NOT rely on your outside knowledge of the category. If the source content does not explicitly support something, omit it.
- If a requested section cannot be supported from the source material, write a concise clearly qualified statement that this section is not fully supported by the provided sources.
- Use the authoritative vendor list only; do not introduce vendors not included there.

COMPREHENSIVE CONTENT REQUIREMENTS:
- Each section should be grounded in evidence from the source text.
- Prefer accuracy and faithfulness over length. Do not artificially inflate content just to hit a word count.
- Structure content with clear subheadings, bullet points, and logical flow for easy consumption.
- Use examples and vendors only when they are explicitly supported by the source text.

DETAILED SECTION REQUIREMENTS:
1. DEFINITION: 4-6 comprehensive paragraphs describing what the SOFTWARE does, its core purpose, evolution, and strategic importance in the modern business landscape.

2. CORE CAPABILITIES: 12-20 separate capability statements. Return core_capabilities as a JSON list of individual capability items. Each list item should be a single capability statement, written clearly and concisely with explanation, benefit, use case, and implementation consideration using strong function verbs. Do not combine multiple capabilities into one paragraph.

3. BOUNDARIES: Exhaustive analysis of adjacent categories with specific examples, detailed comparison matrices, clear differentiation criteria, and guidance on when to choose this category vs alternatives.

4. BUYER/USE CASE: Extremely detailed breakdown of buyer personas (titles, roles, responsibilities), use cases by industry/company size, buying journey stages, decision-making processes, and ROI justification frameworks.

5. REPRESENTATIVE VENDORS: List ONLY companies from the AUTHORITATIVE VENDOR LIST in the user message. One bullet per vendor with positioning (Leader/Challenger/Specialist) supported by sources. Never invent vendors not in that list. Do not list social/ad platforms, generic CRM/ERP, or vendors from adjacent categories unless they are on the authoritative list.

6. MARKET OVERVIEW: Deep dive into market size (TAM/SAM/SOM), growth rates, adoption patterns, and drivers. When naming vendors, use ONLY the authoritative vendor list — do not mention random enterprise brands as category vendors.

7. IMPLEMENTATION CONSIDERATIONS: Comprehensive technical requirements, integration needs, change management strategies, organizational considerations, skills/training requirements, and risk mitigation approaches.

8. VENDOR LANDSCAPE: Analyze market structure using ONLY vendors from the authoritative list; do not introduce vendors absent from that list.

9. FUTURE TRENDS: Thorough examination of emerging technologies, regulatory impacts, evolving buyer behaviors, and long-term category evolution with specific timeline predictions.

10. INTEGRATION POINTS: Detailed mapping of how this category connects with other systems (CRM, ERP, marketing automation, analytics, etc.), including technical standards, data models, and implementation best practices.

11. SUCCESS METRICS: Extensive framework of specific KPIs, measurement approaches, benchmark data, and guidance on building effective measurement systems across short-term and long-term horizons.

12. COMMON CHALLENGES: Deep exploration of implementation hurdles, organizational barriers, technical limitations, and proven mitigation strategies with real-world examples.

13. CATEGORY DRIFT: Sophisticated analysis of analyst disagreement on scope, evolution of definitions over time, and implications for buyers and vendors.

Return valid JSON matching the schema with extremely detailed content for each field."""),
        ("human", """Category: {category}
Aliases: {aliases}

AUTHORITATIVE VENDOR LIST for "{category}" (extracted from sources below — use ONLY these in representative_vendors and when naming category vendors elsewhere):
{category_vendors}

Sources:
{sources_text}

Use only the content provided above. Do not add material from outside knowledge.

Synthesize an extraordinarily comprehensive category page (aim for 3000-5000+ words total) from these sources, following all the detailed requirements above."""),
    ])
    
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    structured_llm = llm.with_structured_output(CategoryPageModel)
    chain = COMPREHENSIVE_SYNTHESIS_PROMPT | structured_llm
    
    cache_key_parts = (
        "synthesis_v4_category_vendors",
        TEST_CATEGORY,
        str(len(synthesis_sources)),
        vendors_block[:500],
        sources_text[:3000],
    )
    cached = cache_get("llm_synthesis", *cache_key_parts)
    
    if cached is not None:
        synthesis = cached
    else:
        try:
            synthesis = chain.invoke({
                "category": TEST_CATEGORY,
                "aliases": ", ".join(CATEGORY_ALIASES),
                "category_vendors": vendors_block,
                "sources_text": sources_text,
            })
            cache_set("llm_synthesis", synthesis.model_dump(), *cache_key_parts)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")

    synthesis_out = synthesis if isinstance(synthesis, dict) else synthesis.model_dump()
    synthesis_out["source_count"] = len(synthesis_sources)
    synthesis_out = apply_authoritative_vendors_to_synthesis(
        synthesis_out, category_vendors, TEST_CATEGORY
    )

    return {
        "sources_used": len(synthesis_sources),
        "synthesis_top_n": SYNTHESIS_TOP_N,
        "category_vendors": category_vendors,
        "synthesis_sources": synthesis_source_links,
        "synthesis": synthesis_out,
    }

@app.post("/workflow/full")
async def run_full_workflow():
    """Run the complete workflow end-to-end"""
    # Step 1: Search
    search_results = await search_sources()
    
    # Step 2: Scrape
    scrape_results = await scrape_sources([SearchResult(**r) for r in search_results["results"]])
    
    # Step 3: Deduplicate
    dedupe_results = await deduplicate_sources([ScrapedSource(**s) for s in scrape_results["scraped_sources"]])
    
    # Step 4: Score
    score_results = await score_sources([ScrapedSource(**s) for s in dedupe_results["deduped_sources"]])
    
    # Step 5: Synthesize
    synthesis_results = await synthesize_category(score_results["scored_sources"])
    
    return {
        "search": search_results,
        "scrape": scrape_results,
        "deduplicate": dedupe_results,
        "score": score_results,
        "synthesize": synthesis_results,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
