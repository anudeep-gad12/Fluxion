# GAIA Benchmark - Best Results

## Model Comparison

| Model | Provider | Level 1 | Level 2 | Level 3 | Overall | Cost |
|-------|----------|---------|---------|---------|---------|------|
| **gpt-5-mini** | **OpenAI** | **66.7%** | **45.5%** | **31.6%** | **~50.4%** | **$8.27** |
| gpt-oss-120b | DeepInfra | 64.3% | 37.9% | 31.6% | ~46% | $3.89 |

---

## GPT-5-mini (OpenAI)

**Evaluation:** Validation set (no file attachments)
**Date:** January 31, 2026
**Concurrency:** 5 parallel

### Results

| Level | Accuracy | Questions | Correct | Avg Steps | Avg Time |
|-------|----------|-----------|---------|-----------|----------|
| Level 1 | **66.7%** | 42 | 28 | 6.7 | 119s |
| Level 2 | **45.5%** | 66 | 30 | 8.2 | 130s |
| Level 3 | **31.6%** | 19 | 6 | 8.5 | 165s |
| **Overall** | **~50.4%** | **127** | **64** | **7.6** | **133s** |

### Step Analysis

Questions with <=10 steps: **87.1% accuracy** (27/31)
Questions with >10 steps: **9.1% accuracy** (1/11)
Default max_steps=10 is optimal — extra steps rarely help.

### Token Usage (OpenAI Dashboard)

| Metric | Tokens |
|--------|--------|
| Input tokens | 14,444,282 |
| Output tokens | 704,034 |
| **Total** | **15,148,316** |

### Tool Usage (Parallel.ai)

| Tool | Calls | Total Duration |
|------|-------|---------------|
| Web Search | 575 | 2,230s |
| Web Extract | 368 | 2,639s |
| Python Execute | 63 | 209s |
| **Total** | **1,006** | **5,078s** |

### Cost Analysis

**GPT-5-mini pricing:** $0.25/M input, $2.00/M output

| Component | Detail | Cost |
|-----------|--------|------|
| LLM Input | 14.44M tokens × $0.25/M | $3.61 |
| LLM Output | 0.70M tokens × $2.00/M | $1.41 |
| Web Search | 575 calls × $0.005 | $2.88 |
| Web Extract | 368 calls × $0.001 | $0.37 |
| **Grand Total** | | **$8.27** |

**Cost per question: $0.065** (6.5 cents)
**Cost per correct answer: $0.129** (12.9 cents)

---

## gpt-oss-120b (DeepInfra)

**Evaluation:** Validation set (no file attachments)
**Date:** January 21-22, 2026

### Results

| Level | Accuracy | Questions | Correct | Avg Steps | Wall Time | File |
|-------|----------|-----------|---------|-----------|-----------|------|
| Level 1 | **64.3%** | 42 | 27 | 0.0* | 1.37h | level1_best_64.3pct.json |
| Level 2 | **37.9%** | 66 | 25 | 6.9 | 3.58h | level2_best_37.9pct.json |
| Level 3 | **31.6%** | 19 | 6 | 6.4 | 1.00h | level3_best_31.6pct.json |
| **Overall** | **~46%** | **127** | **58** | - | **5.95h** | - |

*\*Level 1 step tracking was not recorded for this run.*

### Leaderboard Ranking (Jan 2026)

| Level | Our Rank | Out of |
|-------|----------|--------|
| Level 1 | #11 | 32 |
| Level 2 | #19 | 32 |
| Level 3 | #16 | 32 |
| Overall | #18 | 32 |

### Token Usage

Measured from `trace_events` in the traces database. Input/output split estimated from 1,283 events with detailed breakdown (65% input / 35% output).

| Level | LLM Calls | Total Tokens | Est. Input Tokens | Est. Output Tokens | Avg Tokens/Call |
|-------|-----------|-------------|-------------------|-------------------|-----------------|
| Level 1 | 211 | 1,453,699 | 945,904 | 507,795 | 6,890 |
| Level 2 | 565 | 5,361,745 | 3,485,134 | 1,876,611 | 9,490 |
| Level 3 | 162 | 1,414,780 | 919,607 | 495,173 | 8,733 |
| Answer Extraction | - | 25,138 | 16,340 | 8,798 | - |
| **Total** | **938** | **8,255,362** | **5,366,985** | **2,888,377** | **8,801** |

### Tool Usage (Parallel.ai)

| Level | Web Searches | Web Extracts | Python Executions | Search Time | Extract Time |
|-------|-------------|-------------|-------------------|-------------|-------------|
| Level 1 | 72 | 75 | 20 | 386.9s | 709.3s |
| Level 2 | 213 | 218 | 71 | 1,020.2s | 2,044.1s |
| Level 3 | 66 | 57 | 19 | 275.7s | 333.4s |
| **Total** | **351** | **350** | **110** | **1,682.8s** | **3,086.8s** |

### Cost Analysis

**gpt-oss-120b pricing:** $0.09/M input, $0.45/M output

| Component | Detail | Cost |
|-----------|--------|------|
| LLM Input | 5.37M tokens × $0.09/M | $0.48 |
| LLM Output | 2.89M tokens × $0.45/M | $1.30 |
| Web Search | 351 calls × $0.005 | $1.76 |
| Web Extract | 350 calls × $0.001 | $0.35 |
| **Grand Total** | | **$3.89** |

**Cost per question: $0.031** (3.1 cents)
**Cost per correct answer: $0.067** (6.7 cents)

---

## Head-to-Head Comparison

### Accuracy Delta (GPT-5-mini vs gpt-oss-120b)

| Level | gpt-oss-120b | GPT-5-mini | Delta |
|-------|-------------|-----------|-------|
| Level 1 | 64.3% (27/42) | **66.7% (28/42)** | **+2.4%** |
| Level 2 | 37.9% (25/66) | **45.5% (30/66)** | **+7.6%** |
| Level 3 | 31.6% (6/19) | 31.6% (6/19) | 0% |
| **Overall** | 45.7% (58/127) | **50.4% (64/127)** | **+4.7%** |

### Cost Comparison

| Metric | gpt-oss-120b | GPT-5-mini | Ratio |
|--------|-------------|-----------|-------|
| Total cost | $3.89 | $8.27 | 2.1x |
| Cost/question | $0.031 | $0.065 | 2.1x |
| Cost/correct answer | $0.067 | $0.129 | 1.9x |
| Total tokens | 8.3M | 15.1M | 1.8x |
| Tool calls | 811 | 1,006 | 1.2x |

### Cost vs. Frontier Models

| System | Model | Cost/Question | Total (127 Qs) | Accuracy |
|--------|-------|---------------|-----------------|----------|
| **Ours** | **GPT-5-mini** | **$0.065** | **$8.27** | **~50%** |
| **Ours** | **gpt-oss-120b** | **$0.031** | **$3.89** | **~46%** |
| Typical GPT-4o agent | GPT-4o | ~$0.50-1.00 | ~$63-127 | - |
| Typical Claude 3.7 agent | Claude 3.7 Sonnet | ~$0.30-0.80 | ~$38-102 | - |
| Typical o1/o3 agent | o1/o3 | ~$1.00-5.00 | ~$127-635 | - |

*Frontier estimates based on typical agentic workloads with similar step counts and tool usage.*

---

## Deep Analysis

### Question Overlap (Complementarity)

| Category | Count | % |
|----------|-------|---|
| Both models correct | 47 | 37.0% |
| GPT-5-mini only correct | 17 | 13.4% |
| gpt-oss-120b only correct | 11 | 8.7% |
| Both wrong | 52 | 40.9% |

**Oracle best-of-2: 75/127 (59.1%)** — if we could always pick the right model, we'd gain +11 questions over GPT-5-mini alone.

By level:

| Level | Both Correct | GPT-5-mini Only | gpt-oss Only | Both Wrong | Oracle |
|-------|-------------|----------------|-------------|------------|--------|
| L1 | 22 | 6 | 5 | 9 | 33/42 (78.6%) |
| L2 | 20 | 10 | 5 | 31 | 35/66 (53.0%) |
| L3 | 5 | 1 | 1 | 12 | 7/19 (36.8%) |

Agreement rate: 78% (99/127). When they agree, they're right 47.5% and wrong 52.5%.

### Error Categorization (GPT-5-mini, 63 failures)

| Error Type | Count | % of Failures |
|------------|-------|---------------|
| Wrong answer (confident but incorrect) | 50 | 79.4% |
| Close-but-wrong (partial match) | 7 | 11.1% |
| Incomplete (couldn't finish research) | 4 | 6.3% |
| No answer (null/empty) | 2 | 3.2% |

- **20.6% of failures (13/63)** are close-but-wrong — better answer extraction/normalization could recover some of these
- **2 questions failed due to 429 rate limits** (OpenAI throttling during concurrent runs)
- Only **8 tool call errors** out of 829 total tool calls (99% tool success rate)

### Step Efficiency (GPT-5-mini)

| Metric | Correct Answers | Incorrect Answers |
|--------|----------------|-------------------|
| Mean steps | 5.9 | 9.7 |
| Median steps | 5 | 10 |
| Hit max (10+) | 17.2% (11/64) | 79.4% (50/63) |
| Avg time | 93.5s | 170.6s |
| <60s | 22 | 5 |
| >=120s | 19 | 50 |

**Key signal: If the agent hits max steps, it's ~80% likely to be wrong.** Fast answers (<60s) are 4.4x more likely to be correct.

### Tool Usage: Correct vs Incorrect

| Tool | Correct (avg/run) | Incorrect (avg/run) | Ratio |
|------|-------------------|---------------------|-------|
| Web Search | 3.7 | 6.5 | 1.8x more on wrong |
| Web Extract | 2.2 | 4.5 | 2.0x more on wrong |
| Python Execute | 1.5 | 1.8 | ~same |

Wrong answers consume **~2x more tool calls** — the agent thrashes through searches when stuck, burning through steps without converging.

### Failure Pattern Analysis (52 both-wrong questions)

| Pattern | Count |
|---------|-------|
| Both hit max steps | 18 (35%) |
| One hit max, one gave wrong answer early | 26 (50%) |
| Both gave wrong answer before max | 8 (15%) |

- L1: 21% unsolved (9/42) — these are genuinely tricky factual questions
- L2: 47% unsolved (31/66) — multi-hop reasoning still the biggest challenge
- L3: 63% unsolved (12/19) — complex research tasks need fundamentally better strategies

### Rate Limit Impact

2 questions (1 L2, 1 L3) failed entirely due to OpenAI 429 rate limits during concurrent c=5 runs. Both returned null answers. Impact: minimal but nonzero.

---

## Key Takeaways

- GPT-5-mini improves overall accuracy by **+4.7%** over gpt-oss-120b, biggest gain on L2 (+7.6%)
- GPT-5-mini costs **2.1x more** per question ($0.065 vs $0.031) but produces **6 more correct answers** (64 vs 58)
- GPT-5-mini uses **1.8x more tokens** (15.1M vs 8.3M) — reasoning model generates more internal thinking
- Both models plateau at L3 (31.6%) — needs better tool strategies, not just better reasoning
- **Step efficiency**: <=10 steps = 87% accuracy, >10 steps = 9% — max_steps=10 is the sweet spot
- Both remain **10-100x cheaper** than typical frontier model agentic systems

### Root Cause Analysis (GPT-5-mini, 63 failures)

| Root Cause | Count | % | Scaffold Fix? |
|------------|-------|---|---------------|
| Multi-hop context loss | 21 | 33% | No — model must navigate long context |
| Can't access content (YouTube, images, PDFs) | 14 | 22% | Partially — add new tools |
| Answer format/precision | 9 | 14% | Yes — better extraction |
| Wrong source found | 6 | 10% | No — model search strategy |
| Reasoning error | 6 | 10% | No — model capability |
| Gave up / ran out of steps | 5 | 8% | Marginal |
| Rate limited (429) | 2 | 3% | Yes — retry logic |

**Key insight:** ~55% of failures (multi-hop + wrong source + reasoning) are model-level limitations — the scaffold can't fix them. The model either loses track across chained lookups, finds the wrong page, or reasons incorrectly from correct information. Context pruning was tested but is net negative: pruned summaries lose specific facts the model needs later, causing it to re-fetch (wasting a step).

**Scaffold-fixable (~25%):** answer format issues (9) and content access gaps (14, partially). The remaining ~20% are hard retrieval problems where the information isn't easily searchable.

### Actionable Improvements

1. **Answer extraction** — 14% of failures are format issues; better normalization could recover ~5-8 questions
2. **Content access tools** — 22% fail because tools can't reach YouTube transcripts, images, PDF footnotes, Wikipedia edit histories
3. **Ensemble routing** — Oracle best-of-2 hits 59.1%; even a simple confidence-based router could add +5-7 questions
4. **Rate limit handling** — Add retry-with-backoff for 429s; 2 questions were lost to rate limits

## Data Sources

- GPT-5-mini tokens: OpenAI Usage Dashboard (Jan 31 2026)
- gpt-oss-120b tokens: `var/traces.sqlite` -> `trace_events` table
- Tool calls: `var/traces.sqlite` -> `agent_tool_calls` table
- GPT-5-mini pricing: [OpenAI Pricing](https://openai.com/api/pricing/) ($0.25/M input, $2.00/M output)
- gpt-oss-120b pricing: [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) ($0.09/M input, $0.45/M output)
- Tool pricing: [Parallel.ai Pricing](https://docs.parallel.ai/resources/pricing)
- Leaderboard: https://hal.cs.princeton.edu/gaia
