"""
Streamlit application for Category Definition workflow
Showcases every step's inputs and outputs from the API
"""

import streamlit as st
import requests
import json
from datetime import datetime

# API base URL
API_BASE = "http://localhost:8000"

# Page configuration
st.set_page_config(
    page_title="Category Definition Workflow",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .step-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        margin: 1rem 0;
    }
    .metric-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #667eea;
    }
    .success-box {
        background: #d4edda;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #28a745;
    }
    .warning-box {
        background: #fff3cd;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #ffc107;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if 'workflow_step' not in st.session_state:
    st.session_state.workflow_step = 0
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'scrape_results' not in st.session_state:
    st.session_state.scrape_results = None
if 'dedupe_results' not in st.session_state:
    st.session_state.dedupe_results = None
if 'score_results' not in st.session_state:
    st.session_state.score_results = None
if 'synthesis_results' not in st.session_state:
    st.session_state.synthesis_results = None
if 'evaluation_results' not in st.session_state:
    st.session_state.evaluation_results = None

# Sidebar
st.sidebar.title("📊 Category Definition")
st.sidebar.markdown("---")

# Configuration section
st.sidebar.header("Configuration")
config_response = requests.get(f"{API_BASE}/config")
if config_response.status_code == 200:
    config = config_response.json()
    category = st.sidebar.text_input("Category", value=config.get("category", "Account-Based Marketing"))
    maturity = st.sidebar.selectbox("Maturity", ["emerging", "evolving", "stable"], index=["emerging", "evolving", "stable"].index(config.get("maturity", "evolving")))
    max_age = st.sidebar.number_input("Max Source Age (months)", value=config.get("max_source_age_months", 24))
    
    # Display how aliases are split
    focused_aliases = config.get("focused_aliases", [])
    secondary_aliases = config.get("secondary_aliases", [])
    if focused_aliases or secondary_aliases:
        st.sidebar.markdown("**Alias Splitting:**")
        st.sidebar.markdown(f"- **Focused (first 2):** {', '.join(focused_aliases)}")
        st.sidebar.markdown(f"- **Secondary (remaining):** {', '.join(secondary_aliases)}")
        st.sidebar.markdown("---")
    
    # Aliases input - display current aliases as comma-separated or newline-separated
    current_aliases = config.get("aliases", [])
    aliases_text = st.sidebar.text_area(
        "Aliases (one per line or comma-separated)",
        value="\n".join(current_aliases) if current_aliases else "",
        height=150,
        help="Enter category aliases, one per line or separated by commas. First 2 will be used for focused search, rest for secondary search."
    )
    
    if st.sidebar.button("Update Configuration"):
        # Parse aliases from text area (split by newlines or commas)
        parsed_aliases = [alias.strip() for alias in aliases_text.replace(",", "\n").split("\n") if alias.strip()]
        requests.post(f"{API_BASE}/config", json={
            "category": category,
            "maturity": maturity,
            "aliases": parsed_aliases,
            "max_source_age_months": max_age,
        })
        st.sidebar.success("Configuration updated!")

st.sidebar.markdown("---")
st.sidebar.header("Cache Stats")
cache_response = requests.get(f"{API_BASE}/cache/stats")
if cache_response.status_code == 200:
    cache_stats = cache_response.json()
    for namespace, count in cache_stats.items():
        st.sidebar.metric(namespace, count)

st.sidebar.markdown("**Clear Cache:**")
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("🗑️ LLM", help="Clear LLM scoring cache only"):
        requests.delete(f"{API_BASE}/cache", params={"namespace": "llm_scoring"})
        st.sidebar.success("LLM cache cleared!")
        st.rerun()
with col2:
    if st.button("🗑️ All", help="Clear all cache"):
        requests.delete(f"{API_BASE}/cache")
        st.sidebar.success("All cache cleared!")
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("Navigation")
if st.sidebar.button("🔄 Reset Workflow"):
    st.session_state.workflow_step = 0
    st.session_state.search_results = None
    st.session_state.scrape_results = None
    st.session_state.dedupe_results = None
    st.session_state.score_results = None
    st.session_state.synthesis_results = None
    st.rerun()

# Main content
st.title("📊 Category Definition Workflow")
st.markdown("This application showcases the complete workflow for defining software categories using trusted sources, LLM scoring, and synthesis.")

# Progress bar
steps = ["Search", "Scrape", "Deduplicate", "Score", "Synthesize"]
progress = st.session_state.workflow_step / len(steps)
st.progress(progress)

# Step 0: Search
if st.session_state.workflow_step >= 0:
    st.markdown('<div class="step-header"><h2>Step 1: Search for Sources</h2></div>', unsafe_allow_html=True)
    
    if st.button("🔍 Run Search", key="search_btn"):
        with st.spinner("Searching for sources..."):
            response = requests.post(f"{API_BASE}/search")
            if response.status_code == 200:
                st.session_state.search_results = response.json()
                st.session_state.workflow_step = 1
                st.rerun()
            else:
                st.error(f"Search failed: {response.text}")
    
    if st.session_state.search_results:
        results = st.session_state.search_results
        st.markdown(f'<div class="success-box">✅ Search complete: {results["total_queries"]} queries → {results["total_urls"]} URLs found</div>', unsafe_allow_html=True)
        
        with st.expander("View Search Results"):
            for i, result in enumerate(results["results"]):
                st.markdown(f"""
                **{i+1}. [{result['search_pass']}] {result['title']}**
                - URL: {result['url']}
                - Alias: {result['query_alias']}
                - Snippet: {result['snippet'][:100]}...
                """)

# Step 1: Scrape
if st.session_state.workflow_step >= 1:
    st.markdown('<div class="step-header"><h2>Step 2: Scrape Content</h2></div>', unsafe_allow_html=True)
    
    if st.button("🕷️ Run Scraping", key="scrape_btn"):
        with st.spinner("Scraping content from URLs..."):
            response = requests.post(f"{API_BASE}/scrape", json=st.session_state.search_results["results"])
            if response.status_code == 200:
                st.session_state.scrape_results = response.json()
                st.session_state.workflow_step = 2
                st.rerun()
            else:
                st.error(f"Scraping failed: {response.text}")
    
    if st.session_state.scrape_results:
        results = st.session_state.scrape_results
        st.markdown(f'''
        <div class="metric-card">
            <strong>Scrape Results:</strong>
            <ul>
                <li>Original URLs: {results['original_count']}</li>
                <li>Pre-scrape filtered: {results['pre_scrape_filtered']}</li>
                <li>Attempted to scrape: {results['attempted_scrape']}</li>
                <li>Successfully scraped: {results['successfully_scraped']}</li>
                <li>Post-scrape filtered: {results['post_scrape_filtered']}</li>
                <li>Success rate: {results['successfully_scraped']/results['original_count']*100:.1f}%</li>
            </ul>
        </div>
        ''', unsafe_allow_html=True)
        
        with st.expander("View Pre-scrape Filtered"):
            for item in results['pre_scrape_details']:
                st.markdown(f"✗ **{item['reason']}:** {item['title'][:60]}")
                st.text(item['url'])
        
        with st.expander("View Successfully Scraped URLs"):
            for i, item in enumerate(results['scraped_sources']):
                st.markdown(f"**{i+1}.** [{item['title']}]({item['url']})")
                st.caption(f"Alias: {item['query_alias']} | Pass: {item['search_pass']}")
        
        with st.expander("View Post-scrape Failures"):
            for item in results['scrape_failures']:
                st.markdown(f"✗ **{item['reason']}:** {item['url']}")

# Step 2: Deduplicate
if st.session_state.workflow_step >= 2:
    st.markdown('<div class="step-header"><h2>Step 3: Deduplicate Content</h2></div>', unsafe_allow_html=True)
    
    if st.button("🔀 Run Deduplication", key="dedupe_btn"):
        with st.spinner("Deduplicating content..."):
            response = requests.post(f"{API_BASE}/deduplicate", json=st.session_state.scrape_results["scraped_sources"])
            if response.status_code == 200:
                st.session_state.dedupe_results = response.json()
                st.session_state.workflow_step = 3
                st.rerun()
            else:
                st.error(f"Deduplication failed: {response.text}")
    
    if st.session_state.dedupe_results:
        results = st.session_state.dedupe_results
        st.markdown(f'''
        <div class="success-box">
            ✅ Deduplication complete: {results['before_count']} → {results['after_count']} sources ({results['duplicates_removed']} duplicates removed)
        </div>
        ''', unsafe_allow_html=True)

# Step 3: Score
if st.session_state.workflow_step >= 3:
    st.markdown('<div class="step-header"><h2>Step 4: Score Sources with LLM</h2></div>', unsafe_allow_html=True)
    
    if st.button("🎯 Run Scoring", key="score_btn"):
        with st.spinner("Scoring sources with LLM..."):
            response = requests.post(f"{API_BASE}/score", json=st.session_state.dedupe_results["deduped_sources"])
            if response.status_code == 200:
                st.session_state.score_results = response.json()
                st.session_state.workflow_step = 4
                st.rerun()
            else:
                st.error(f"Scoring failed: {response.text}")
    
    if st.session_state.score_results:
        results = st.session_state.score_results
        st.markdown(f'''
        <div class="metric-card">
            <strong>Scoring Results:</strong>
            <ul>
                <li>Total scored: {results['total_scored']}</li>
                <li>Cache hits: {results['cache_hits']}</li>
                <li>New LLM calls: {results['new_llm_calls']}</li>
            </ul>
        </div>
        ''', unsafe_allow_html=True)
        
        # Display top sources
        st.markdown("### Top Sources by Relevance")
        for i, item in enumerate(results['scored_sources'][:5]):
            s = item['source']
            sc = item['score']
            st.markdown(f"""
            **#{i+1} - Relevance: {sc['relevance_score']}/10 | Slots: {sc['slots_filled']}/5 | Vendors: {sc['vendor_count']}**
            - **Title:** {s['title']}
            - **URL:** {s['url']}
            - **Author:** {s['author'] or 'n/a'}
            - **Date:** {s['date'] or 'n/a'}
            - **Host:** {s['hostname']}
            - **Byline:** {sc['byline_quality']} | Expert verbs: {sc['uses_function_verbs']} | SME: {sc['is_sme_content']} | Bias: {sc['single_vendor_bias']}
            - **Vendors:** {', '.join(sc['vendor_names']) if sc['vendor_names'] else 'None'}
            - **Reasoning:** {sc['reasoning']}
            """)
        
        with st.expander("View All Scored Sources"):
            for i, item in enumerate(results['scored_sources']):
                s = item['source']
                sc = item['score']
                with st.expander(f"#{i+1} - {s['title'][:60]}... (Relevance: {sc['relevance_score']}/10)"):
                    st.json(item)

# Step 4: Synthesize
if st.session_state.workflow_step >= 4:
    st.markdown('<div class="step-header"><h2>Step 5: Synthesize Category Page</h2></div>', unsafe_allow_html=True)
    
    if st.button("📝 Run Synthesis", key="synthesize_btn"):
        with st.spinner("Synthesizing comprehensive category page..."):
            response = requests.post(f"{API_BASE}/synthesize", json=st.session_state.score_results["scored_sources"])
            if response.status_code == 200:
                st.session_state.synthesis_results = response.json()
                st.session_state.workflow_step = 5
                st.rerun()
            else:
                st.error(f"Synthesis failed: {response.text}")
    
    if st.session_state.synthesis_results:
        results = st.session_state.synthesis_results
        synthesis = results['synthesis']
        
        st.markdown(f'''
        <div class="success-box">
            ✅ Synthesis complete using {results['sources_used']} high-quality sources
        </div>
        ''', unsafe_allow_html=True)
        
        # Display synthesis
        st.markdown("## Comprehensive Category Page")
        st.markdown(f"### {synthesis['category_name']}")
        st.markdown(f"**Aliases:** {', '.join(synthesis['aliases'])}")
        st.markdown(f"**Confidence:** {synthesis['confidence']} | **Sources:** {synthesis['source_count']}")
        
        # Display source links
        st.markdown("---")
        st.markdown("### Source Links Used")
        if st.session_state.score_results:
            top_sources = [
                item for item in st.session_state.score_results['scored_sources']
                if item['score']['relevance_score'] >= 5
                and item['score']['slots_filled'] >= 2
                and not item['score']['single_vendor_bias']
            ]
            if len(top_sources) < 3:
                top_sources = [
                    item for item in st.session_state.score_results['scored_sources']
                    if item['score']['relevance_score'] >= 5
                    and item['score']['slots_filled'] >= 2
                ]
            for i, item in enumerate(top_sources[:5]):
                s = item['source']
                sc = item['score']
                st.markdown(f"**{i+1}.** [{s['title']}]({s['url']}) - Relevance: {sc['relevance_score']}/10")
        
        st.markdown("---")
        
        sections = [
            ("1. DEFINITION", synthesis['definition']),
            ("2. CORE CAPABILITIES", "\n".join(f"• {cap}" for cap in synthesis['core_capabilities'])),
            ("3. BOUNDARIES", synthesis['boundaries']),
            ("4. BUYER / USE CASE", synthesis['buyer_use_case']),
            ("5. REPRESENTATIVE VENDORS", "\n".join(f"• {vendor}" for vendor in synthesis['representative_vendors'])),
            ("6. MARKET OVERVIEW", synthesis['market_overview']),
            ("7. IMPLEMENTATION CONSIDERATIONS", synthesis['implementation_considerations']),
            ("8. VENDOR LANDSCAPE", synthesis['vendor_landscape']),
            ("9. FUTURE TRENDS", synthesis['future_trends']),
            ("10. INTEGRATION POINTS", synthesis['integration_points']),
            ("11. SUCCESS METRICS", synthesis['success_metrics']),
            ("12. COMMON CHALLENGES", synthesis['common_challenges']),
            ("13. CATEGORY DRIFT / ANALYST DISAGREEMENT", synthesis['category_drift']),
        ]
        
        for section_title, section_content in sections:
            with st.expander(section_title):
                st.markdown(section_content)
        
        with st.expander("View Raw Synthesis JSON"):
            st.json(synthesis)
        
        # Evaluation section
        st.markdown("---")
        st.markdown('<div class="step-header"><h2>Step 6: Evaluate Synthesis Quality</h2></div>', unsafe_allow_html=True)
        
        if st.button("📊 Run Evaluation", key="eval_btn"):
            with st.spinner("Evaluating synthesis quality..."):
                try:
                    # Import and use the evaluator
                    import sys
                    sys.path.append('.')
                    from ai import evaluate_synthesis
                    
                    # Extract source content from scored sources that were used in synthesis
                    source_content = []
                    if st.session_state.score_results:
                        scored_sources = st.session_state.score_results.get('scored_sources', [])
                        # Get sources that were actually used in synthesis (high quality)
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
                        # Convert to the format expected by evaluator (url, title, text)
                        for item in top_sources[:5]:  # Limit to top 5 sources
                            source = item["source"]
                            source_content.append({
                                "url": source.get("url", ""),
                                "title": source.get("title", ""),
                                "text": source.get("text", "")[:2000]  # Limit text length
                            })
                    
                    evaluation_results = evaluate_synthesis(synthesis, synthesis['category_name'], source_content)
                    st.session_state.evaluation_results = evaluation_results
                    st.rerun()
                except Exception as e:
                    st.error(f"Evaluation failed: {str(e)}")
        
        if st.session_state.evaluation_results:
            results = st.session_state.evaluation_results
            
            if 'error' in results:
                st.markdown(f'''
                <div class="warning-box">
                    ⚠️ Evaluation completed with warnings: {results["error"]}
                </div>
                ''', unsafe_allow_html=True)
            else:
                st.markdown(f'''
                <div class="success-box">
                    ✅ Evaluation complete: Overall Score {results["overall_score"]}/10
                </div>
                ''', unsafe_allow_html=True)
                
                # Display evaluation metrics
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### Evaluation Scores")
                    metrics = [
                        ("Definition Clarity", results.get("definition_clarity", 0)),
                        ("Core Capabilities", results.get("core_capabilities", 0)),
                        ("Boundaries", results.get("boundaries", 0)),
                        ("Buyer/Use Case", results.get("buyer_use_case", 0)),
                        ("Representative Vendors", results.get("representative_vendors", 0)),
                        ("Market Overview", results.get("market_overview", 0)),
                        ("Implementation Considerations", results.get("implementation_considerations", 0)),
                        ("Vendor Landscape", results.get("vendor_landscape", 0)),
                        ("Future Trends", results.get("future_trends", 0)),
                        ("Integration Points", results.get("integration_points", 0)),
                        ("Success Metrics", results.get("success_metrics", 0)),
                        ("Common Challenges", results.get("common_challenges", 0)),
                        ("Category Drift", results.get("category_drift", 0)),
                        ("Overall Coherence", results.get("overall_coherence", 0)),
                        ("Source Utilization", results.get("source_utilization", 0)),
                        ("Faithfulness", results.get("faithfulness", 0)),
                        ("Coverage", results.get("coverage", 0))
                    ]
                    
                    for label, value in metrics:
                        st.metric(label, f"{value}/10")
                
                with col2:
                    # Create a simple visualization
                    st.markdown("### Overall Score")
                    score = results.get("overall_score", 0)
                    st.metric("Overall Evaluation Score", f"{score}/10")
                    
                    # Performance indicator
                    if score >= 8.0:
                        st.success("Excellent quality synthesis")
                    elif score >= 6.0:
                        st.warning("Good quality synthesis")
                    elif score >= 4.0:
                        st.info("Fair quality synthesis")
                    else:
                        st.error("Poor quality synthesis")
                
                # Detailed reasoning expander
                with st.expander("View Evaluation Details"):
                    st.json(results)

# Full workflow button
st.markdown("---")
st.markdown("### Quick Actions")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🚀 Run Complete Workflow", type="primary"):
        with st.spinner("Running complete workflow..."):
            response = requests.post(f"{API_BASE}/workflow/full")
            if response.status_code == 200:
                full_results = response.json()
                st.session_state.search_results = full_results['search']
                st.session_state.scrape_results = full_results['scrape']
                st.session_state.dedupe_results = full_results['deduplicate']
                st.session_state.score_results = full_results['score']
                st.session_state.synthesis_results = full_results['synthesize']
                st.session_state.workflow_step = 5
                st.success("Complete workflow finished successfully!")
                st.rerun()
            else:
                st.error(f"Workflow failed: {response.text}")

with col2:
    if st.button("📥 Export Synthesis"):
        if st.session_state.synthesis_results:
            synthesis = st.session_state.synthesis_results['synthesis']
            st.download_button(
                label="Download Synthesis as JSON",
                data=json.dumps(synthesis, indent=2),
                file_name=f"category_definition_{synthesis['category_name'].replace(' ', '_')}.json",
                mime="application/json"
            )

with col3:
    if st.button("💾 Export All Steps"):
        # Check if we have workflow results
        if (st.session_state.search_results is not None and 
            st.session_state.scrape_results is not None and 
            st.session_state.dedupe_results is not None and
            st.session_state.score_results is not None and
            st.session_state.synthesis_results is not None):
            
            # Compile all results into a single dictionary
            complete_results = {
                "search": st.session_state.search_results,
                "scrape": st.session_state.scrape_results,
                "deduplicate": st.session_state.dedupe_results,
                "score": st.session_state.score_results,
                "synthesize": st.session_state.synthesis_results
            }
            
            # Add timestamp
            complete_results["export_timestamp"] = datetime.now().isoformat()
            
            st.download_button(
                label="Download Complete Workflow as JSON",
                data=json.dumps(complete_results, indent=2),
                file_name=f"category_workflow_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
        else:
            # If we don't have all results, offer to run the full workflow first
            if st.button("Run Full Workflow to Export"):
                with st.spinner("Running complete workflow..."):
                    response = requests.post(f"{API_BASE}/workflow/full")
                    if response.status_code == 200:
                        full_results = response.json()
                        st.session_state.search_results = full_results['search']
                        st.session_state.scrape_results = full_results['scrape']
                        st.session_state.dedupe_results = full_results['deduplicate']
                        st.session_state.score_results = full_results['score']
                        st.session_state.synthesis_results = full_results['synthesize']
                        st.session_state.workflow_step = 5
                        
                        # Now prepare the download
                        complete_results = {
                            "search": st.session_state.search_results,
                            "scrape": st.session_state.scrape_results,
                            "deduplicate": st.session_state.dedupe_results,
                            "score": st.session_state.score_results,
                            "synthesize": st.session_state.synthesis_results
                        }
                        
                        # Add timestamp
                        complete_results["export_timestamp"] = datetime.now().isoformat()
                        
                        st.download_button(
                            label="Download Complete Workflow as JSON",
                            data=json.dumps(complete_results, indent=2),
                            file_name=f"category_workflow_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json"
                        )
                    else:
                        st.error(f"Workflow failed: {response.text}")

# Footer
st.markdown("---")
st.markdown("""
**Category Definition Workflow**  
Built with FastAPI + Streamlit + LangChain + OpenAI  
Based on trusted source methodology for software category definition
""")
