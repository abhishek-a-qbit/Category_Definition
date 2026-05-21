import sys
sys.path.append('.')

# Test the evaluation module still works
from ai import evaluate_synthesis

# Mock synthesis data for testing
mock_synthesis = {
    "category_name": "Account-Based Marketing",
    "aliases": ["ABM", "Account-Based Everything"],
    "definition": "Account-Based Marketing (ABM) is a strategic approach that coordinates personalized marketing and sales efforts to engage specific target accounts.",
    "core_capabilities": ["Target account identification", "Personalized campaign orchestration", "Sales and marketing alignment"],
    "boundaries": "ABM differs from broad-based marketing by focusing on high-value accounts rather than wide lead generation.",
    "buyer_use_case": "B2B companies use ABM to increase deal size and win rates with strategic enterprise accounts.",
    "representative_vendors": ["6sense", "Demandbase", "Terminus"],
    "category_drift": "Some analysts debate whether ABM includes only technology platforms or also encompasses services.",
    "market_overview": "The ABM market is growing rapidly as B2B companies seek more efficient sales approaches.",
    "implementation_considerations": "Successful ABM requires data quality, sales-marketing alignment, and proper technology stack.",
    "vendor_landscape": "The ABM vendor landscape includes pure-play platforms and modules within larger marketing suites.",
    "future_trends": "AI-driven personalization and intent data integration are emerging trends in ABM.",
    "integration_points": "ABM platforms integrate with CRM, marketing automation, and advertising systems.",
    "success_metrics": "Key metrics include pipeline velocity, deal size, win rates, and ROI from target accounts.",
    "common_challenges": "Common challenges include data silos, measurement difficulties, and organizational alignment.",
    "source_count": 5,
    "confidence": "high"
}

# Mock source content in the format that will be passed from app.py (scraped content)
mock_source_content = [
    {
        "url": "https://www.gartner.com/en/articles/the-account-based-everything-framework",
        "title": "The Account-Based Everything Framework",
        "text": "Account-Based Marketing (ABM) is a strategic approach that focuses resources on a set of target accounts within a market. It uses personalized campaigns designed to engage each account, basing the marketing message on the specific attributes and needs of the account. ABM aligns sales and marketing efforts to increase revenue from high-value accounts."
    },
    {
        "url": "https://www.forrester.com/blogs/author/john_arnold/",
        "title": "ABM Best Practices for 2024",
        "text": "Effective ABM requires deep understanding of target accounts, personalized content creation, and close sales-marketing alignment. Key capabilities include account identification, insight generation, and personalized orchestration. Technologies like 6sense and Demandbase help scale ABM efforts."
    },
    {
        "url": "https://research.isg-one.com/analyst-perspectives/topic/intelligent-marketing",
        "title": "Intelligent Marketing Trends",
        "text": "The ABM landscape continues to evolve with AI-driven personalization and intent data playing increasingly important roles. Implementation considerations include data quality, technology stack integration, and change management. Common challenges involve measurement difficulties and organizational silos."
    }
]

# Test evaluation
try:
    result = evaluate_synthesis(mock_synthesis, "Account-Based Marketing", mock_source_content)
    print("Full evaluation result:")
    print(result)
    print()
    print("Evaluation successful!")
    print(f"Overall score: {result.get('overall_score', 'N/A')}/10")
    
    # Check individual scores
    criteria = [
        'definition_clarity', 'core_capabilities', 'boundaries', 'buyer_use_case',
        'representative_vendors', 'market_overview', 'implementation_considerations',
        'vendor_landscape', 'future_trends', 'integration_points', 'success_metrics',
        'common_challenges', 'category_drift', 'overall_coherence', 'source_utilization',
        'faithfulness', 'coverage'
    ]
    
    missing = [key for key in criteria if key not in result]
    if missing:
        print(f"Missing criteria: {missing}")
    else:
        print("All criteria present!")
        for key in criteria:
            print(f"  {key}: {result.get(key, 'MISSING')}/10")
    
    # Verify overall score is in 0-10 range
    overall = result.get('overall_score', 0)
    if 0 <= overall <= 10:
        print(f"\nPASS: Overall score {overall} is within valid range (0-10)")
    else:
        print(f"\nFAIL: Overall score {overall} is outside valid range (0-10)")
        
    # Check that faithfulness and coverage are present
    if 'faithfulness' in result and 'coverage' in result:
        print(f"Faithfulness/Groundedness: {result['faithfulness']}/10")
        print(f"Coverage: {result['coverage']}/10")
    else:
        print("ERROR: Faithfulness or coverage missing!")
        
except Exception as e:
    print(f"Evaluation failed: {e}")
    import traceback
    traceback.print_exc()