"""
FastAPI application for Category Definition workflow
Based on test.ipynb - searches, scrapes, scores, and synthesizes category definitions
"""

import os
import hashlib
import json
import pathlib
import time
import requests
from datetime import datetime
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

ANALYST_HUB_URLS = [
    "https://www.forrester.com/blogs/author/john_arnold/",
    "https://www.forrester.com/blogs/author/jessie_johnson/",
    "https://www.forrester.com/blogs/author/terry_flaherty/",
    "https://www.gartner.com/en/articles/the-account-based-everything-framework",
    "https://research.isg-one.com/analyst-perspectives/topic/intelligent-marketing",
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
    analyst_hub_urls: List[str] = ANALYST_HUB_URLS

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

def should_scrape_url(url: str, title: str, search_pass: str) -> Tuple[bool, str]:
    url_lower = url.lower()
    for pattern in DROP_URL_PATTERNS:
        if pattern in url_lower:
            return False, f"DROP_URL_PATTERN: {pattern}"
    
    hostname = urlparse(url).netloc.lower()
    for blocked in SERPER_EXCLUDE_SITES:
        if blocked in hostname:
            return False, f"BLOCKED_DOMAIN: {blocked}"
    
    non_content_patterns = [
        "/page/", "/category/", "/tag/", "/author/",
        "/search", "/login", "/register", "/contact",
        "/privacy", "/terms", "/about", "/careers",
        "/events", "/webinars", "/podcasts", "/videos",
        "/download", "/pdf", "/whitepaper", "/ebook",
        "/trial", "/demo", "/pricing", "/buy",
        "/cart", "/checkout", "/payment", "/subscribe"
    ]
    
    for pattern in non_content_patterns:
        if pattern in url_lower:
            return False, f"NON_CONTENT_PATTERN: {pattern}"
    
    if not title or len(title.strip()) < 10:
        return False, "SHORT_OR_MISSING_TITLE"
    
    if search_pass.startswith("Tier2"):
        if "blog" not in url_lower and "article" not in url_lower and "research" not in url_lower:
            return False, "TIER2_NON_CONTENT_URL"
    
    return True, "PASS"

def should_keep_scraped_content(article: Dict, max_age_months: int) -> Tuple[bool, str]:
    if not article or "_error" in article:
        return False, f"SCRAPE_ERROR: {article.get('_error', 'unknown')}"
    
    text = article.get("text", "")
    if not text or len(text) < 300:
        return False, f"TOO_SHORT: {len(text)} chars"
    
    date_str = article.get("date")
    if date_str:
        age = source_age_months(date_str)
        if age is not None and age > max_age_months:
            return False, f"TOO_OLD: {age} months (max: {max_age_months})"
    
    author = article.get("author", "")
    hostname = article.get("hostname", "")
    
    if any(analyst in hostname for analyst in ["gartner", "forrester", "idc", "constellation", "isg-one"]):
        if not author or len(author.strip()) < 3:
            return False, "ANALYST_SITE_NO_AUTHOR"
    
    return True, "PASS"

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
        "secondary_aliases": SECONDARY_ALIASES,
        "analyst_hub_urls": ANALYST_HUB_URLS
    }

@app.post("/config")
async def update_config(config: CategoryConfig):
    """Update category configuration"""
    global TEST_CATEGORY, CATEGORY_MATURITY, CATEGORY_ALIASES, MAX_SOURCE_AGE_MONTHS, FOCUSED_ALIASES, SECONDARY_ALIASES, ANALYST_HUB_URLS
    TEST_CATEGORY = config.category
    CATEGORY_MATURITY = config.maturity
    CATEGORY_ALIASES = config.aliases
    MAX_SOURCE_AGE_MONTHS = config.max_source_age_months
    ANALYST_HUB_URLS = config.analyst_hub_urls
    
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
    
    # Pass 0: Analyst hub URLs
    for hub_url in ANALYST_HUB_URLS:
        if hub_url not in seen_urls and not url_is_blocked(hub_url):
            seen_urls.add(hub_url)
            all_results.append({
                "url": hub_url,
                "title": f"[Hub] {hub_url.split('/')[-2] if hub_url.endswith('/') else hub_url.split('/')[-1]}",
                "snippet": "",
                "query_alias": TEST_CATEGORY,
                "search_pass": "AnalystHub",
            })
    
    # Pass 1: Tier 1 primary aliases
    def run_search_pass(name: str, sites: List[str], aliases: List[str], batch_size: int, num_per_query: int = 6):
        nonlocal total_queries
        batches = batch_site_queries(sites, batch_size=batch_size)
        queries_run = 0
        hits_added = 0
        blocked = 0
        
        for alias in aliases:
            for site_clause in batches:
                query = f'{site_clause} "{alias}" {SERPER_EXCLUSIONS}'
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
    
    run_search_pass("Tier1-primary", TIER1_SITES, FOCUSED_ALIASES, batch_size=3)
    run_search_pass("Tier1-secondary", TIER1_SITES, SECONDARY_ALIASES, batch_size=3)
    run_search_pass("Tier2-key", KEY_TIER2_SITES, FOCUSED_ALIASES, batch_size=5)
    run_search_pass("Tier2-key", KEY_TIER2_SITES, SECONDARY_ALIASES, batch_size=5)
    
    return {
        "total_queries": total_queries,
        "total_urls": len(all_results),
        "results": all_results,
    }

@app.post("/scrape")
async def scrape_sources(search_results: List[SearchResult]):
    """Step 2: Scrape content from search results"""
    filtered_for_scraping = []
    pre_scrape_filtered = []
    
    for result in search_results:
        should_scrape, reason = should_scrape_url(result.url, result.title, result.search_pass)
        
        if should_scrape:
            filtered_for_scraping.append(result)
        else:
            pre_scrape_filtered.append({
                "url": result.url,
                "title": result.title,
                "reason": reason,
                "search_pass": result.search_pass
            })
    
    scraped_sources = []
    scrape_failures = []
    
    for result in filtered_for_scraping:
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
    
    return {
        "original_count": len(search_results),
        "pre_scrape_filtered": len(pre_scrape_filtered),
        "attempted_scrape": len(filtered_for_scraping),
        "successfully_scraped": len(scraped_sources),
        "post_scrape_filtered": len(scrape_failures),
        "scraped_sources": scraped_sources,
        "pre_scrape_details": pre_scrape_filtered[:10],
        "scrape_failures": scrape_failures[:10],
    }

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

Score it on these criteria:
1. SLOT-FILL: Does it contain (a) a definition, (b) core capabilities, (c) boundaries vs adjacent categories, (d) buyer/use case, (e) representative vendors? Count how many of these 5 slots it fills.
2. FUNCTION-VERBS: Does it use expert verbs (orchestrate, unify, score, route, match, segment, personalize, align) rather than SEO adjectives?
3. BYLINE QUALITY: Evaluate the author byline - "named_analyst", "named_author", or "no_byline".
4. VENDOR DIVERSITY: How many distinct vendors are named? CRITICAL: Extract ACTUAL vendor/product names from the content. Look for company names like "Salesforce", "HubSpot", "Adobe", "Marketo", "6sense", "Demandbase", etc. Do NOT use placeholders like "Vendor 1, Vendor 2". If the text mentions specific companies, list their exact names. If no vendors are mentioned, return an empty list []. Examples of correct output: ["Salesforce", "HubSpot", "Adobe"] or [] if none found.
5. SME CONTENT: Is this analyst/expert content or marketing fluff?
6. RELEVANCE: How useful is this source (1-10)?

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
    
    for i, s in enumerate(sources):
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
        
        cache_key_parts = ("scoring_v2", TEST_CATEGORY, s.url, s.title or "Unknown",
                           s.author or "Unknown", s.date or "Unknown",
                           s.hostname or "Unknown", text_trunc)
        cached = cache_get("llm_scoring", *cache_key_parts)
        
        if cached is not None:
            score_data = cached["score"] if "score" in cached else cached
            score = SourceScoreModel(**score_data)
            cache_hits += 1
            scored_sources.append({"source": s.model_dump(), "score": score.model_dump()})
            continue
        
        try:
            score = chain.invoke(invoke_params)
            rendered_msgs = SCORING_PROMPT.format_messages(**invoke_params)
            rendered_prompt = "\n".join(f"[{m.type}] {m.content}" for m in rendered_msgs)
            cache_set("llm_scoring", {
                "score": score.model_dump(),
                "prompt": rendered_prompt,
            }, *cache_key_parts)
            scored_sources.append({"source": s.model_dump(), "score": score.model_dump()})
            time.sleep(LLM_DELAY)
        except Exception as e:
            pass
    
    # Sort by relevance score descending
    scored_sources.sort(key=lambda x: x["score"]["relevance_score"], reverse=True)
    
    return {
        "total_scored": len(scored_sources),
        "cache_hits": cache_hits,
        "new_llm_calls": len(scored_sources) - cache_hits,
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
        representative_vendors: list[str] = Field(description="Named vendors from multiple sources")
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
    
    # Select top sources for synthesis
    top_sources = [
        item for item in scored_sources
        if item["score"]["relevance_score"] >= 5
        and item["score"]["slots_filled"] >= 2
        and not item["score"]["single_vendor_bias"]
    ]
    
    if len(top_sources) < 3:
        top_sources = [
            item for item in scored_sources
            if item["score"]["relevance_score"] >= 5
            and item["score"]["slots_filled"] >= 2
        ]
    
    # Prepare source summaries for synthesis
    source_summaries = []
    for item in top_sources[:5]:
        s = item["source"]
        sc = item["score"]
        source_summaries.append(f"""
Source: {s['title']}
Author: {s['author']}
URL: {s['url']}
Relevance: {sc['relevance_score']}/10
Slots filled: {sc['slots_filled']}/5
Vendors: {', '.join(sc['vendor_names'])}
Content: {s['text'][:2000]}...
""")
    
    sources_text = "\n".join(source_summaries)
    
    COMPREHENSIVE_SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages([
        ("system", """You are writing a comprehensive category definition page. The page must be written in editorial voice — no direct quotation from sources. Multi-source consensus carries definition.

COMPREHENSIVE CONTENT REQUIREMENTS:
- Each section should be substantial (3-6 paragraphs) with detailed insights
- Use specific examples, vendor names, and concrete scenarios
- Provide actionable insights for buyers and implementers

DETAILED SECTION REQUIREMENTS:
1. DEFINITION: 2-4 sentences describing what the SOFTWARE does.
2. CORE CAPABILITIES: 6-10 detailed capabilities using function-verbs.
3. BOUNDARIES: Comprehensive analysis of adjacent categories with specific examples.
4. BUYER/USE CASE: Detailed breakdown of buyer personas and use cases.
5. REPRESENTATIVE VENDORS: Comprehensive vendor list with categorization.
6. MARKET OVERVIEW: Market size, growth rates, adoption patterns.
7. IMPLEMENTATION CONSIDERATIONS: Technical requirements, integration needs.
8. VENDOR LANDSCAPE: Analysis of market structure and competitive dynamics.
9. FUTURE TRENDS: Emerging technologies and category evolution.
10. INTEGRATION POINTS: How this category connects with other systems.
11. SUCCESS METRICS: Specific KPIs and measurement approaches.
12. COMMON CHALLENGES: Implementation hurdles and mitigation strategies.
13. CATEGORY DRIFT: Analysis of analyst disagreement on scope.

Return valid JSON matching the schema."""),
        ("human", """Category: {category}
Aliases: {aliases}

Sources:
{sources_text}

Synthesize a comprehensive category page from these sources."""),
    ])
    
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    structured_llm = llm.with_structured_output(CategoryPageModel)
    chain = COMPREHENSIVE_SYNTHESIS_PROMPT | structured_llm
    
    cache_key_parts = ("synthesis_v2", TEST_CATEGORY, str(len(top_sources)), sources_text[:1000])
    cached = cache_get("llm_synthesis", *cache_key_parts)
    
    if cached is not None:
        synthesis = cached
    else:
        try:
            synthesis = chain.invoke({
                "category": TEST_CATEGORY,
                "aliases": ", ".join(CATEGORY_ALIASES),
                "sources_text": sources_text,
            })
            cache_set("llm_synthesis", synthesis.model_dump(), *cache_key_parts)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")
    
    return {
        "sources_used": len(top_sources),
        "synthesis": synthesis if isinstance(synthesis, dict) else synthesis.model_dump(),
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
