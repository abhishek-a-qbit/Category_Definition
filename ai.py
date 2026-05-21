"""
Evaluation module for grading LLM synthesis outputs
Uses LLM as a judge to evaluate category definition quality
"""

import os
import json
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env")

class EvaluationCriteria(BaseModel):
    """Schema for evaluation scores"""
    definition_clarity: int = Field(description="Clarity and accuracy of category definition (1-10)")
    core_capabilities: int = Field(description="Completeness and relevance of core capabilities (1-10)")
    boundaries: int = Field(description="Clarity of category boundaries vs adjacent categories (1-10)")
    buyer_use_case: int = Field(description="Quality of buyer persona and use case description (1-10)")
    representative_vendors: int = Field(description="Accuracy and diversity of vendor examples (1-10)")
    market_overview: int = Field(description="Insightfulness of market analysis (1-10)")
    implementation_considerations: int = Field(description="Usefulness of implementation guidance (1-10)")
    vendor_landscape: int = Field(description="Depth of vendor ecosystem analysis (1-10)")
    future_trends: int = Field(description="Foresight in identifying emerging trends (1-10)")
    integration_points: int = Field(description="Clarity of integration requirements (1-10)")
    success_metrics: int = Field(description="Measurability of success metrics (1-10)")
    common_challenges: int = Field(description="Relevance of identified challenges (1-10)")
    category_drift: int = Field(description="Quality of analyst disagreement analysis (1-10)")
    overall_coherence: int = Field(description="Overall coherence and readability of the synthesis (1-10)")
    source_utilization: int = Field(description="Effective use of source materials (1-10)")
    faithfulness: int = Field(description="Faithfulness/groundedness: Does the synthesis stick to the information in the sources? Does it hallucinate or add facts not in the sources? (1-10)")
    coverage: int = Field(description="Coverage: Does the synthesis cover the key points from the sources? Does it miss important information? (1-10)")
    overall_score: float = Field(description="Weighted overall score (0-10)")

class SynthesisEvaluator:
    def __init__(self):
        self.llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0, api_key=OPENAI_API_KEY)
        self.parser = JsonOutputParser(pydantic_object=EvaluationCriteria)
        
        self.evaluation_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert evaluator of software category definitions. 
            Your task is to evaluate a synthesized category page based on the following criteria:
            
            1. Definition clarity and accuracy (1-10): Is the definition clear, concise, and accurate?
            2. Core capabilities (1-10): Are the core capabilities comprehensive and relevant?
            3. Boundaries (1-10): How well does it distinguish from adjacent categories?
            4. Buyer/use case (1-10): Quality of buyer persona and use case description
            5. Representative vendors (1-10): Accuracy and diversity of vendor examples
            6. Market overview (1-10): Insightfulness of market analysis
            7. Implementation considerations (1-10): Usefulness of implementation guidance
            8. Vendor landscape (1-10): Depth of vendor ecosystem analysis
            9. Future trends (1-10): Foresight in identifying emerging trends
            10. Integration points (1-10): Clarity of integration requirements
            11. Success metrics (1-10): Measurability of success metrics
            12. Common challenges (1-10): Relevance of identified challenges
            13. Category drift (1-10): Quality of analyst disagreement analysis
            14. Overall coherence (1-10): Overall readability and flow
            15. Source utilization (1-10): Effective use of source materials
            16. Faithfulness/Groundedness (1-10): Does the synthesis stick to the information in the sources? Does it hallucinate or add facts not in the sources?
            17. Coverage (1-10): Does the synthesis cover the key points from the sources? Does it miss important information?
            
            Provide scores for each criterion and an overall weighted score (0-10).
            The overall score should be weighted as follows:
            - Definition clarity and accuracy: 12% (0.12)
            - Core capabilities: 12% (0.12)
            - Boundaries: 8% (0.08)
            - Buyer/use case: 8% (0.08)
            - Representative vendors: 8% (0.08)
            - Market overview: 8% (0.08)
            - Implementation considerations: 4% (0.04)
            - Vendor landscape: 4% (0.04)
            - Future trends: 4% (0.04)
            - Integration points: 2.4% (0.024)
            - Success metrics: 2.4% (0.024)
            - Common challenges: 2.4% (0.024)
            - Category drift: 2.4% (0.024)
            - Overall coherence: 1.6% (0.016)
            - Source utilization: 1.6% (0.016)
            - Faithfulness: 8% (0.08)
            - Coverage: 8% (0.08)
            
            Return valid JSON matching the schema with exactly these field names:
            definition_clarity, core_capabilities, boundaries, buyer_use_case, representative_vendors,
            market_overview, implementation_considerations, vendor_landscape, future_trends,
            integration_points, success_metrics, common_challenges, category_drift, overall_coherence,
            source_utilization, faithfulness, coverage, overall_score"""),
            ("human", """Category: {category}
            
            Source Content:
            {source_content}
            
            Synthesis to evaluate:
            {synthesis_json}
            
            Evaluate this synthesis based on the criteria, comparing it to the source content."""),
        ])
        
        self.chain = self.evaluation_prompt | self.llm | self.parser
    
    def evaluate(self, synthesis: Dict[str, Any], category: str, source_content: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluate a synthesis output
        
        Args:
            synthesis: The synthesis dictionary from the API
            category: The category name
            source_content: List of source dictionaries containing url, title, text, etc.
            
        Returns:
            Dictionary with evaluation scores
        """
        try:
            # Format synthesis for evaluation
            synthesis_text = json.dumps(synthesis, indent=2)
            
            # Format source content for evaluation (limit to avoid token issues)
            source_parts = []
            for i, source in enumerate(source_content[:5]):  # Limit to top 5 sources
                source_text = source.get('text', '')[:1500]  # Limit text length
                source_parts.append(f"""
Source {i+1}:
Title: {source.get('title', 'Unknown')}
URL: {source.get('url', 'Unknown')}
Content: {source_text}...
---""")
            
            source_content_text = "\n".join(source_parts) if source_parts else "No source content provided"
            
            result = self.chain.invoke({
                "category": category,
                "source_content": source_content_text,
                "synthesis_json": synthesis_text
            })
            
            # Calculate weighted overall score
            weights = {
                'definition_clarity': 0.12,
                'core_capabilities': 0.12,
                'boundaries': 0.08,
                'buyer_use_case': 0.08,
                'representative_vendors': 0.08,
                'market_overview': 0.08,
                'implementation_considerations': 0.04,
                'vendor_landscape': 0.04,
                'future_trends': 0.04,
                'integration_points': 0.024,
                'success_metrics': 0.024,
                'common_challenges': 0.024,
                'category_drift': 0.024,
                'overall_coherence': 0.016,
                'source_utilization': 0.016,
                'faithfulness': 0.08,
                'coverage': 0.08
            }
            
            weighted_sum = 0.0
            for criterion, weight in weights.items():
                if criterion in result:
                    weighted_sum += result[criterion] * weight
            
            # Ensure overall_score is set to the weighted sum (0-10 scale)
            result['overall_score'] = round(weighted_sum, 2)
            
            return result
            
        except Exception as e:
            # Return default evaluation on error
            return {
                "definition_clarity": 5,
                "core_capabilities": 5,
                "boundaries": 5,
                "buyer_use_case": 5,
                "representative_vendors": 5,
                "market_overview": 5,
                "implementation_considerations": 5,
                "vendor_landscape": 5,
                "future_trends": 5,
                "integration_points": 5,
                "success_metrics": 5,
                "common_challenges": 5,
                "category_drift": 5,
                "overall_coherence": 5,
                "source_utilization": 5,
                "faithfulness": 5,
                "coverage": 5,
                "overall_score": 5.0,
                "error": str(e)
            }

# Convenience function for direct use
def evaluate_synthesis(synthesis: Dict[str, Any], category: str, source_content: List[Dict[str, Any]]) -> Dict[str, Any]:
    evaluator = SynthesisEvaluator()
    return evaluator.evaluate(synthesis, category, source_content)