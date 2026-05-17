# Test Notebook Pseudocode - Easy English Explanation

This document explains what the `test.ipynb` notebook does.

---

## Overview

The notebook is a system that researches a software category (like "Account-Based Marketing") by:
1. Searching for articles from trusted analyst websites
2. Scraping and filtering the content
3. Using AI to score the quality of each source
4. Synthesizing the best sources into a comprehensive category definition

---

## Step 1: Install Dependencies (Cell 1)

**What it does:**
- Installs the Python packages needed for the notebook to work
- Packages include: python-dotenv, langchain, langchain-openai, trafilatura

**In plain English:**
"Download and install the tools we need to run this notebook."

---

## Step 2: Load API Keys (Cell 2)

**What it does:**
- Reads environment variables from a `.env` file
- Gets the OpenAI API key (for AI processing)
- Gets the Serper API key (for Google search)
- Gets the OpenAI model name (which AI to use)
- Checks that both keys exist - stops if they're missing

**In plain English:**
"Get the secret keys needed to talk to OpenAI and Google Search. Make sure they exist before continuing."

---

## Step 3: Set Up Cache (Cell 2b)

**What it does:**
- Creates a folder called `.cache` to store results
- Makes functions to save and retrieve cached data
- Uses a hash (like a fingerprint) to identify each unique request
- Shows how many cached items exist

**In plain English:**
"Create a storage system to remember previous results. This saves money by not calling paid APIs twice for the same request."

---

## Step 4: Configure Category and Trusted Sources (Cell 3)

**What it does:**
- Sets the category to research: "Account-Based Marketing"
- Sets the maturity level: "evolving" (affects how old sources can be)
- Lists all the different names for this category (aliases)
- Organizes trusted websites into tiers:
  - **Tier 1**: Major analysts (Gartner, Forrester, IDC) - highest quality
  - **Tier 2**: Independent analysts
  - **Tier 2b**: Domain specialists
  - **Tier 4**: Consultancies (McKinsey, BCG, etc.)
  - **Tier 5**: Academic sites (Harvard, MIT, NIST)
- Lists specific analyst author pages to crawl directly
- Creates lists of URLs to BLOCK (review sites, paywalls, vendor sites)
- Creates exclusion rules for Google search (what to exclude)
- Sets the maximum age for sources based on maturity (24 months for "evolving")

**In plain English:**
"Set up what we're researching (Account-Based Marketing) and where we'll look for information. We only trust certain websites and will block others. We also decide how old the information can be."

---

## Step 5: Search for URLs (Cell 4)

**What it does:**
- Creates a function to call the Serper Google Search API
- Creates a function to batch websites into groups for searching
- Creates a function to check if a URL is blocked
- Creates a function to check if a URL is from an allowed website
- Runs multiple search passes:
  - **Pass 0**: Adds direct analyst author hub URLs (no search needed)
  - **Pass 1**: Searches Tier 1 sites with primary aliases
  - **Pass 1b**: Searches Tier 1 sites with secondary aliases
  - **Pass 2**: Searches key Tier 2 sites with primary aliases
- For each search pass:
  - Creates Google search queries with site restrictions
  - Adds exclusion rules to filter out junk
  - Checks cache first to avoid duplicate API calls
  - Only keeps URLs from the explicitly allowed sites
  - Blocks URLs matching drop patterns
  - Removes duplicate URLs
- Verifies all results are from allowed sites
- Shows summary of how many URLs were found

**In plain English:**
"Search Google for articles about Account-Based Marketing, but ONLY from the trusted websites we listed. Run multiple searches with different search terms. Check our cache first to save money. Make sure every result is from a trusted source."

---

## Step 6: Pre-Scraping Filters (Cell 5)

**What it does:**
- Creates a function to download and extract article content using Trafilatura
- Creates a function to calculate how old an article is (in months)
- Creates a function to decide if a URL should be scraped (pre-scraping filter):
  - **Filter 1**: Check if URL matches drop patterns (block if yes)
  - **Filter 2**: Check if domain is blocked (block if yes)
  - **Filter 3**: Check if URL is a non-content page (like /page/, /category/, /author/) - block if yes
  - **Filter 4**: Check if title is too short (less than 10 characters) - block if yes
  - **Filter 5**: Check if title has marketing words (best, top, comparison, etc.) - block if yes
  - **Filter 6**: Tier-based filtering:
    - Tier 1: Allow most URLs
    - Tier 2: Must contain "blog", "article", or "research"
    - Other tiers: Must contain content indicators
- Creates a function to check if scraped content is good quality (post-scraping filter):
  - **Filter 1**: Check if scraping failed - reject if error
  - **Filter 2**: Check if content is too short (less than 300 characters) - reject if yes
  - **Filter 3**: Check if article is too old (older than max age) - reject if yes
  - **Filter 4**: Check if content has too much marketing fluff - reject if yes
  - **Filter 5**: For analyst sites, require a named author - reject if missing
- Applies pre-scraping filters to all URLs
- Scrapes the remaining URLs with Trafilatura
- Applies post-scraping filters to scraped content
- Shows statistics on what was filtered and why

**In plain English:**
"Before scraping, filter out URLs that look like junk (non-content pages, marketing pages, etc.). Then scrape the remaining URLs. After scraping, filter out content that's too short, too old, too marketing-heavy, or missing authors. Keep only the good stuff."

---

## Step 7: Preview Scraped Sources (Cell 6)

**What it does:**
- Loops through all successfully scraped sources
- For each source, displays:
  - Title
  - Author
  - Date
  - Host website
  - Search alias used
  - Content length
  - First part of the content (preview)

**In plain English:**
"Show a summary of all the articles we successfully scraped so we can see what we have."

---

## Step 8: Remove Duplicate Content (Cell 6b)

**What it does:**
- Creates a function to make a "fingerprint" (hash) of the first 500 characters
- Compares fingerprints to find near-identical content
- Removes duplicates
- Replaces the original list with the deduplicated list
- Shows how many duplicates were removed

**In plain English:**
"Check if any articles are basically the same (have identical beginnings). Remove the duplicates so we don't waste time processing the same content twice."

---

## Step 9: Additional Quality Filtering (Cell 7)

**What it does:**
- Creates a function to calculate source age in months
- Creates a function to decide if a source should be kept:
  - Check if URL matches drop patterns - reject if yes
  - Check if content is too short (less than 300 characters) - reject if yes
  - Check if content is too old (older than 1.5x the max age) - reject if yes
- Applies this filter to all deduplicated sources
- Shows which sources were dropped and why
- Shows the final list of filtered sources

**In plain English:**
"Do one more quality check on the sources. Drop anything that's too short, too old, or matches our block patterns. Show what we kept and what we dropped."

---

## Step 10: AI-Based Quality Scoring (Cell 8)

**What it does:**
- Defines a data structure for scoring sources
- Creates a detailed prompt for the AI to evaluate each source
- The AI scores each source on:
  - **Slot-fill**: Does it have definition, capabilities, boundaries, buyer info, vendors? (0-5 slots)
  - **Function-verbs**: Does it use expert words (orchestrate, unify, score) vs marketing words (better, smarter)?
  - **Byline quality**: Is the author a recognized analyst, named author, or anonymous?
  - **Vendor diversity**: How many different vendors are named? Is there single-vendor bias?
  - **SME content**: Is this expert content or marketing fluff?
  - **Relevance**: How useful is this for defining the category? (1-10 score)
- For each source:
  - Check cache first to see if we already scored it
  - If not cached, send to AI with the first 3000 characters
  - Cache the result
  - Add the score to the list
- Sort all sources by relevance score (highest first)
- Show scoring summary

**In plain English:**
"Use AI to carefully evaluate each source. Check if it has the right information, uses expert language, has a credible author, mentions multiple vendors, and is actually useful. Give each source a score and sort them from best to worst."

---

## Step 11: Display Scored Sources (Cell 9)

**What it does:**
- Loops through all scored sources (sorted by relevance)
- For each source, displays:
  - Rank, relevance score, slots filled, vendor count
  - Title, author, date, host, URL
  - Byline quality, expert verbs flag, SME flag, bias flag
  - Which slots were filled (definition, capabilities, etc.)
  - List of vendors named
  - AI's reasoning for the score
- Selects top sources for synthesis:
  - Must have relevance ≥ 5
  - Must fill at least 2 slots
  - Must not have single-vendor bias
  - If too few qualify, relax the bias filter
- Shows how many sources qualify for synthesis

**In plain English:**
"Show a detailed report of each source with its score and why it got that score. Pick the best sources (high relevance, good slot-fill, no bias) to use for creating the final category page."

---

## Step 12: Synthesize Category Page with AI (Cell 11)

**What it does:**
- Defines a data structure for the complete category page
- Creates a detailed prompt for AI to synthesize multiple sources
- The AI must create sections:
  1. Definition (2-4 sentences)
  2. Core capabilities (6-10 detailed items using function-verbs)
  3. Boundaries (what it's NOT, how it differs from adjacent categories)
  4. Buyer/use case (personas, organization types, specific scenarios)
  5. Representative vendors (with categorization and source notes)
  6. Market overview (size, growth, adoption patterns)
  7. Implementation considerations (technical needs, timeline, resources)
  8. Vendor landscape (market structure, consolidation, competition)
  9. Future trends (emerging tech, buyer expectations, 2-3 year outlook)
  10. Integration points (connections to CRM, ERP, etc.)
  11. Success metrics (KPIs, measurement approaches)
  12. Common challenges (implementation hurdles, mitigation)
  13. Category drift (analyst disagreements with specific firm names)
- Prepares the top sources into a text block for the AI
- Checks cache for existing synthesis
- If not cached:
  - Sends to AI with all source content
  - Caches the result
- Displays the complete synthesized category page
- Shows which sources were used

**In plain English:**
"Take the best sources and use AI to combine them into one comprehensive category definition. The AI must create 13 detailed sections covering everything from definition to future trends. Cache the result so we don't have to regenerate it."

---

## Step 13: Export Results (Cell 11)

**What it does:**
- Creates an `output` folder if it doesn't exist
- Saves the complete category page as a JSON file
- Saves all scored sources as a JSON file (for audit trail)
- Shows where the files were saved

**In plain English:**
"Save the final category page and all the source scores to JSON files so we have a permanent record of what we created."

---

## Step 14: Gap Analysis (Cell 12)

**What it does:**
- Checks the synthesized category page for potential gaps:
  - Is confidence less than "high"?
  - Are there fewer than 5 vendors?
  - Is category drift missing?
  - Are there fewer than 5 capabilities?
  - Are there fewer than 5 qualifying sources?
  - Are sources from fewer than 3 different websites?
  - Are there no Tier 1 analyst sources?
- Lists any gaps found
- Shows source host diversity

**In plain English:**
"Check if the final category page is complete. Look for missing information, low source diversity, or lack of top-tier sources. Flag any gaps that might need follow-up research."

---

## Summary Flow

1. **Setup** → Install tools, get API keys, create cache
2. **Configure** → Define category, list trusted sites, set filters
3. **Search** → Google search for articles from trusted sites only
4. **Filter** → Remove junk URLs, scrape content, filter bad content
5. **Deduplicate** → Remove near-identical articles
6. **Score** → Use AI to evaluate quality and relevance of each source
7. **Select** → Pick the best sources based on scores
8. **Synthesize** → Use AI to combine best sources into comprehensive definition
9. **Export** → Save results to files
10. **Review** → Check for gaps and issues

---

## Key Concepts

- **Trusted Sources**: Only certain websites are considered reliable (analyst firms, consultancies, academics)
- **Tier System**: Higher tier sources get more trust and leniency
- **Filters**: Multiple layers of filtering to remove low-quality content
- **Caching**: Save API results to disk to avoid paying for the same request twice
- **AI Scoring**: Use AI to evaluate source quality objectively
- **Synthesis**: Use AI to combine multiple sources into one coherent document
- **Function-Verbs**: Expert language (orchestrate, unify) vs marketing language (better, faster)
- **Slot-Fill**: Check if source has required information types (definition, capabilities, etc.)
- **Category Drift**: Acknowledge when analysts disagree on category definition

---

## Output Files

The notebook creates:
- `output/account_based_marketing_page.json` - The final synthesized category definition
- `output/account_based_marketing_scores.json` - All source scores for audit trail
- `.cache/` folder - Cached API responses (Serper, LLM scoring, LLM synthesis)
