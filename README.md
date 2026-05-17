# Category Definition Workflow

A comprehensive FastAPI and Streamlit application for defining software categories using trusted sources, LLM scoring, and synthesis. Based on the methodology from `test.ipynb`.

## Features

- **Step-by-step workflow** with clear inputs and outputs at each stage
- **Trusted source search** using Serper API with strict site filtering
- **Content scraping** with Trafilatura and quality filters
- **Deduplication** of near-identical content
- **LLM-based scoring** using OpenAI GPT-4o-mini
- **Comprehensive synthesis** generating detailed category pages
- **Caching** to reduce API costs and improve performance
- **Streamlit UI** for interactive workflow visualization

## Architecture

### Workflow Steps

1. **Search**: Search trusted analyst sites (Gartner, Forrester, IDC, Constellation, etc.) for category-related content
2. **Scrape**: Extract article content using Trafilatura with pre and post-scraping filters
3. **Deduplicate**: Remove near-identical content using MD5 hashing
4. **Score**: Use LLM to score sources on relevance, slot-fill, function verbs, byline quality, and vendor diversity
5. **Synthesize**: Generate comprehensive category page from top-scoring sources

### API Endpoints

- `GET /` - API health check
- `GET /config` - Get current category configuration
- `POST /config` - Update category configuration
- `GET /cache/stats` - Get cache statistics
- `POST /search` - Step 1: Search for sources
- `POST /scrape` - Step 2: Scrape content from URLs
- `POST /deduplicate` - Step 3: Deduplicate content
- `POST /score` - Step 4: Score sources with LLM
- `POST /synthesize` - Step 5: Synthesize category page
- `POST /workflow/full` - Run complete workflow end-to-end

## Installation

1. Clone the repository:
```bash
cd "c:\Users\Abhishek A\Defining_Category"
```

2. Create a virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables in `.env` file:
```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
SERPER_API_KEY=your_serper_api_key_here
```

## Usage

### Running the FastAPI Server

Start the API server:
```bash
python api.py
```

Or using uvicorn directly:
```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### Running the Streamlit App

In a separate terminal, start the Streamlit app:
```bash
streamlit run app.py
```

The Streamlit UI will be available at `http://localhost:8501`

### Using the Streamlit UI

1. **Configure** your category settings in the sidebar
2. **Run Search** to find trusted sources
3. **Run Scraping** to extract content
4. **Run Deduplication** to remove duplicates
5. **Run Scoring** to evaluate source quality
6. **Run Synthesis** to generate the category page
7. **Export Results** to download the synthesis as JSON

Or use the **"Run Complete Workflow"** button to execute all steps automatically.

## Configuration

### Category Configuration

- **Category**: Primary category name (e.g., "Account-Based Marketing")
- **Maturity**: Category maturity level (emerging, evolving, stable) - determines source age threshold
- **Max Source Age**: Maximum age of sources in months (12 for emerging, 24 for evolving, 36 for stable)
- **Aliases**: Alternative names for the category

### Trusted Sources

The system uses a curated list of trusted analyst sites organized by tier:

- **Tier 1**: Gartner, Forrester, IDC (highest value)
- **Tier 2**: Constellation, ISG, GigaOm, Nucleus, Aragon (independent analysts)
- **Analyst Hubs**: Pre-identified high-value author pages

### Filtering Rules

- **URL patterns**: Excludes review platforms, comparison pages, vendor portals
- **Domain exclusions**: Blocks vendor sites, social media, Wikipedia
- **Content quality**: Minimum length, author byline requirements, date currency
- **Marketing fluff**: Filters out promotional content using phrase detection

## Scoring Criteria

Sources are scored on multiple dimensions:

1. **Slot-fill (5 slots)**: Definition, capabilities, boundaries, buyer/use case, vendors
2. **Function verbs**: Uses expert verbs (orchestrate, unify, score) vs SEO adjectives
3. **Byline quality**: named_analyst > named_author > no_byline
4. **Vendor diversity**: Number of distinct vendors mentioned
5. **SME content**: Expert analysis vs marketing fluff
6. **Relevance**: Overall usefulness (1-10 scale)

## Synthesis Output

The synthesis generates a comprehensive category page with 13 sections:

1. Definition
2. Core Capabilities
3. Boundaries
4. Buyer/Use Case
5. Representative Vendors
6. Market Overview
7. Implementation Considerations
8. Vendor Landscape
9. Future Trends
10. Integration Points
11. Success Metrics
12. Common Challenges
13. Category Drift/Analyst Disagreement

## Caching

The system uses disk-based caching to reduce API costs:

- **Serper search results**: Cached by query parameters
- **LLM scoring**: Cached by source content hash
- **LLM synthesis**: Cached by category and source set

Cache statistics are displayed in the Streamlit sidebar.

## API Examples

### Get Configuration
```bash
curl http://localhost:8000/config
```

### Run Search
```bash
curl -X POST http://localhost:8000/search
```

### Run Complete Workflow
```bash
curl -X POST http://localhost:8000/workflow/full
```

## Troubleshooting

### API Not Responding
- Ensure the FastAPI server is running on port 8000
- Check that all environment variables are set in `.env`

### Scraping Failures
- Some sites may block automated scraping (403 errors)
- Check that URLs are from allowed trusted sites
- Verify internet connectivity

### LLM Scoring Errors
- Verify OpenAI API key is valid
- Check API quota/billing
- Ensure model name is correct (gpt-4o-mini)

### Streamlit Connection Issues
- Ensure FastAPI server is running before starting Streamlit
- Check that API_BASE URL in app.py matches server address

## Development

### Project Structure
```
Defining_Category/
├── api.py                 # FastAPI application
├── app.py                 # Streamlit application
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── .env                  # Environment variables (create this)
├── .cache/               # Cache directory (auto-created)
└── test.ipynb           # Original notebook reference
```

### Adding New Categories

1. Update configuration via API or Streamlit sidebar
2. Adjust aliases and maturity level as needed
3. Run the workflow to generate category definition

### Modifying Scoring Criteria

Edit the `SourceScoreModel` and `SCORING_PROMPT` in `api.py` to adjust scoring dimensions and prompts.

## License

This project is based on internal methodology for software category definition.

## Support

For issues or questions, refer to the original `test.ipynb` notebook for detailed methodology documentation.
