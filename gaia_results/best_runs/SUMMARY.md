# GAIA Benchmark - Best Results

**Model:** gpt-oss-120b (DeepInfra)
**Evaluation:** Validation set (no file attachments)
**Date:** January 21-22, 2026

---

## Results

| Level | Accuracy | Questions | Correct | Avg Steps | Wall Time | File |
|-------|----------|-----------|---------|-----------|-----------|------|
| Level 1 | **64.3%** | 42 | 27 | 0.0* | 1.37h | level1_best_64.3pct.json |
| Level 2 | **37.9%** | 66 | 25 | 6.9 | 3.58h | level2_best_37.9pct.json |
| Level 3 | **31.6%** | 19 | 6 | 6.4 | 1.00h | level3_best_31.6pct.json |
| **Overall** | **~46%** | **127** | **58** | - | **5.95h** | - |

*\*Level 1 step tracking was not recorded for this run.*

## Leaderboard Ranking (Jan 2026)

| Level | Our Rank | Out of |
|-------|----------|--------|
| Level 1 | #11 | 32 |
| Level 2 | #19 | 32 |
| Level 3 | #16 | 32 |
| Overall | #18 | 32 |

---

## Token Usage

Measured from `trace_events` in the traces database. Token counts are total (input + output combined) per LLM response. Input/output split estimated from 1,283 events with detailed breakdown (65% input / 35% output).

| Level | LLM Calls | Total Tokens | Est. Input Tokens | Est. Output Tokens | Avg Tokens/Call |
|-------|-----------|-------------|-------------------|-------------------|-----------------|
| Level 1 | 211 | 1,453,699 | 945,904 | 507,795 | 6,890 |
| Level 2 | 565 | 5,361,745 | 3,485,134 | 1,876,611 | 9,490 |
| Level 3 | 162 | 1,414,780 | 919,607 | 495,173 | 8,733 |
| Answer Extraction | - | 25,138 | 16,340 | 8,798 | - |
| **Total** | **938** | **8,255,362** | **5,366,985** | **2,888,377** | **8,801** |

## Tool Usage (Parallel.ai)

| Level | Web Searches | Web Extracts | Python Executions | Search Time | Extract Time |
|-------|-------------|-------------|-------------------|-------------|-------------|
| Level 1 | 72 | 75 | 20 | 386.9s | 709.3s |
| Level 2 | 213 | 218 | 71 | 1,020.2s | 2,044.1s |
| Level 3 | 66 | 57 | 19 | 275.7s | 333.4s |
| **Total** | **351** | **350** | **110** | **1,682.8s** | **3,086.8s** |

---

## Cost Analysis

### LLM Cost (DeepInfra gpt-oss-120b)

Pricing: **$0.09/M input tokens**, **$0.45/M output tokens**

| Level | Input Cost | Output Cost | LLM Subtotal |
|-------|-----------|------------|-------------|
| Level 1 | $0.085 | $0.229 | **$0.314** |
| Level 2 | $0.314 | $0.845 | **$1.158** |
| Level 3 | $0.083 | $0.223 | **$0.306** |
| Answer Extraction | $0.001 | $0.004 | **$0.005** |
| **Total** | **$0.483** | **$1.300** | **$1.783** |

### Parallel.ai Tool Cost

Pricing: **$0.005/search request** (10 results), **$0.001/extract URL**

| Level | Search Cost | Extract Cost | Tool Subtotal |
|-------|-----------|-------------|--------------|
| Level 1 | $0.360 | $0.075 | **$0.435** |
| Level 2 | $1.065 | $0.218 | **$1.283** |
| Level 3 | $0.330 | $0.057 | **$0.387** |
| **Total** | **$1.755** | **$0.350** | **$2.105** |

### Total Cost Summary

| Component | Cost | % of Total |
|-----------|------|-----------|
| LLM (DeepInfra gpt-oss-120b) | $1.78 | 46% |
| Web Search (Parallel.ai) | $1.76 | 45% |
| Web Extract (Parallel.ai) | $0.35 | 9% |
| **Grand Total** | **$3.89** | **100%** |

**Cost per question: $0.031** (3.1 cents)
**Cost per correct answer: $0.067** (6.7 cents)

---

## Cost Comparison vs. Frontier Models

| System | Model | Est. Cost/Question | Est. Total (127 Qs) |
|--------|-------|--------------------|---------------------|
| **Ours** | **gpt-oss-120b** | **$0.031** | **$3.89** |
| Typical GPT-4o agent | GPT-4o | ~$0.50-1.00 | ~$63-127 |
| Typical Claude 3.7 agent | Claude 3.7 Sonnet | ~$0.30-0.80 | ~$38-102 |
| Typical o1/o3 agent | o1/o3 | ~$1.00-5.00 | ~$127-635 |

*Frontier estimates based on typical agentic workloads with similar step counts and tool usage.*

---

## Key Highlights

- L1 performance (#11) competitive with Claude-3.7 Sonnet and Haiku 4.5 systems
- Using open-weight model (gpt-oss-120b) vs. frontier models
- Beats HAL+DeepSeek R1, HAL+DeepSeek V3, HAL+Gemini 2.0 Flash
- **Total benchmark cost: $3.89** -- roughly 10-100x cheaper than frontier model alternatives
- Cost breakdown is nearly 50/50 between LLM inference and web tool usage

## Data Sources

- Token data: `var/traces.sqlite` -> `trace_events` table (matched by question text to best run results)
- Tool calls: `var/traces.sqlite` -> `agent_tool_calls` table
- LLM pricing: [DeepInfra gpt-oss-120b](https://deepinfra.com/openai/gpt-oss-120b) via [llm-stats.com](https://llm-stats.com/models/gpt-oss-120b)
- Tool pricing: [Parallel.ai Pricing](https://docs.parallel.ai/resources/pricing)
- Leaderboard: https://hal.cs.princeton.edu/gaia
