# News Intelligence Desk

A **deterministic workflow orchestration system** for news analysis. Unlike autonomous agents, this system uses explicit code to control all decisions—LLM is only used for semantic extraction and classification.

```
User Query → Router → Workflow Selection → Tool Execution → Verification → Report
```

## Core Design Principles

1. **LLM for extraction, not control flow**: The LLM extracts topics, framings, evidence, and claims. All decisions about what to do next are made by code.

2. **Explicit verification gates**: Before proceeding, data must pass source diversity checks, minimum article thresholds, and schema validation.

3. **Fail fast with abstention**: When data quality is insufficient, the system abstains with a clear reason rather than hallucinating.

4. **Decision-support artifacts**: Output is structured JSON + markdown reports with citations, confidence scores, and explicit limitations.

## Supported Workflows

### 1. Framing Divergence
Analyzes how different news sources frame the same topic.

```bash
python -m newsdesk "How is the AI regulation debate being framed?"
```

**Output includes:**
- Per-source stance analysis (supportive/critical/neutral)
- Clustering of similar perspectives
- Divergence summary
- Citations with relevant quotes

### 2. Claim Check
Verifies factual claims by analyzing evidence from multiple sources.

```bash
python -m newsdesk "Is it true that Tesla recalled 2 million vehicles?"
```

**Output includes:**
- Verdict (supported/contradicted/mixed/unverifiable)
- Supporting and contradicting evidence
- Confidence score with limiting factors
- Citations ranked by relevance

## Installation

```bash
# Clone and enter the directory
cd news_helpdesk

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```bash
# Required: Anthropic API key for LLM
ANTHROPIC_API_KEY=your-key-here

# Optional: NewsAPI key for real news articles
# Without this, mock data is used (fine for testing)
NEWSAPI_KEY=your-newsapi-key
GNEWS_KEY=your-gnews-key
CURRENTS_KEY=your-currents-key
```

## Usage

### Web Interface (Recommended)

```bash
source venv/bin/activate
python run_web.py
# Open http://localhost:8000
```

The web interface provides:
- Clean, minimal UI
- Real-time status updates as analysis progresses
- Formatted markdown reports

### Command Line

```bash
# Activate virtual environment
source venv/bin/activate

# Run with automatic workflow detection
python -m newsdesk "Your query here"

# Force a specific workflow
python -m newsdesk "Your query" --workflow framing
python -m newsdesk "Your query" --workflow claim

# Debug mode (shows all steps)
python -m newsdesk "Your query" --debug

# Output
# - output/output.json (structured data)
# - output/report.md (human-readable report)
```

## Example Runs

### Framing Divergence Example

```bash
$ python -m newsdesk "How is the AI regulation debate being framed?"
```

**Output (summarized):**

```
Perspectives Identified:
- Economic Threat Perspective (TechCrunch, WSJ)
  Themes: threat to innovation, competitive disadvantage

- Consumer Protection Perspective (Consumer Reports, Wired)
  Themes: user safety, necessary protection

Divergence Summary:
The sources split between viewing regulation as harmful constraint
versus necessary protection.
```

### Claim Check Example

```bash
$ python -m newsdesk "Did the company confirm 10,000 layoffs?"
```

**Output (summarized):**

```
Verdict: ⚖️ MIXED

Evidence breakdown: 2 supporting, 2 contradicting

Supporting: Bloomberg, Financial Times confirm ~10,000
Contradicting: CNBC suggests 12,000, Guardian estimates 15,000
```

### Abstention Example

```bash
$ python -m newsdesk "What is the weather today?"
```

**Output:**

```
## ⚠️ Analysis Abstained

Reason: query_ambiguous

Query does not clearly match any supported workflow.
This is a weather query, not a news analysis question.
```

## Abstention Triggers

The system **abstains** (refuses to provide an unreliable answer) when:

| Reason | Description |
|--------|-------------|
| `query_ambiguous` | Query doesn't match any supported workflow |
| `insufficient_sources` | Fewer than 3 articles found |
| `low_source_diversity` | Articles from fewer than 3 unique sources |
| `claim_not_verifiable` | No relevant evidence for the claim |
| `llm_output_invalid` | LLM response failed schema validation after retry |
| `clustering_unstable` | Could not cluster framings consistently |

## Project Structure

```
newsdesk/
├── __main__.py          # CLI entrypoint
├── config.py            # Configuration + .env loading
├── schemas/
│   └── core.py          # Typed data models (Query, Article, Citation, etc.)
├── router/
│   └── classifier.py    # Query → workflow classification
├── llm/
│   └── client.py        # LLM wrapper with schema validation + retry
├── retrieval/
│   ├── client.py        # NewsAPI client with caching
│   └── mock.py          # Mock data for testing
├── verification/
│   └── gates.py         # Source diversity, article count gates
└── workflows/
    ├── framing.py       # Framing Divergence workflow
    └── claim_check.py   # Claim Check workflow
```

## Why Not Just Ask ChatGPT?

This is a fair question. Here's the honest comparison:

| Aspect | ChatGPT / Claude Chat | News Intelligence Desk |
|--------|----------------------|------------------------|
| **Convenience** | Ask anything, get an answer | Requires specific query format |
| **Citations** | May hallucinate sources | Real sources with URLs |
| **Confidence** | Sounds confident always | Explicit confidence + limitations |
| **Abstention** | Rarely abstains | Abstains when data insufficient |
| **Reproducibility** | Varies by session | Deterministic pipeline |
| **Audit trail** | Black box | Step-by-step verification |
| **Scope** | Unlimited topics | Two specific workflows |

**When to use this system:**
- You need verifiable citations
- You want to understand source diversity
- You need confidence scores with explicit limitations
- You prefer abstention over hallucination
- You need reproducible, auditable analysis

**When to just use ChatGPT:**
- Quick, casual information needs
- Topics outside news analysis
- When convenience outweighs verification

## Limitations

1. **Mock data by default**: Without a NewsAPI key, the system uses mock data. Results with mock data have reduced confidence.

2. **Two workflows only**: This MVP supports only Framing Divergence and Claim Check.

3. **English only**: News retrieval and analysis is English-only.

4. **API rate limits**: NewsAPI free tier allows 100 requests/day.

5. **LLM dependency**: Requires Anthropic API access.

6. **Not real-time**: Cached results may be up to 1 hour old.

## Demo Scripts

```bash
# Run all demos
./demos/demo_framing.sh
./demos/demo_claim_check.sh
./demos/demo_abstention.sh
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error |
| 2 | Abstention |

## License

MIT
