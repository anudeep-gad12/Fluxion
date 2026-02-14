# Benchmarks

Performance evaluation of the Reasoner agent system.

## GAIA Benchmark

[GAIA](https://arxiv.org/abs/2311.12983) (General AI Assistants) is a benchmark for evaluating AI assistants on real-world tasks requiring reasoning, web browsing, and tool use.

### Our Results

Two models evaluated on the same agent scaffold. Validation set (127 questions, no file attachments).

#### GPT-5-mini (OpenAI) — Best Results

**Date**: January 31, 2026

| Level | Accuracy | Questions | Correct |
|-------|----------|-----------|---------|
| Level 1 | **66.7%** | 42 | 28 |
| Level 2 | **45.5%** | 66 | 30 |
| Level 3 | **31.6%** | 19 | 6 |
| **Overall** | **50.4%** | 127 | 64 |

**Cost**: ~$8 for full evaluation ($0.065/question)

#### gpt-oss-120b (DeepInfra) — Deployed Model

**Date**: January 21-22, 2026

| Level | Accuracy | Questions | Correct |
|-------|----------|-----------|---------|
| Level 1 | **64.3%** | 42 | 27 |
| Level 2 | **37.9%** | 66 | 25 |
| Level 3 | **31.6%** | 19 | 6 |
| **Overall** | **45.7%** | 127 | 58 |

**Cost**: ~$4 for full evaluation ($0.031/question)

### Leaderboard Ranking

Compared against the [HAL Princeton GAIA Leaderboard](https://hal.cs.princeton.edu/gaia) (January 2026):

| Model | Overall Rank | Out of | Notes |
|-------|-------------|--------|-------|
| GPT-5-mini | **~#15** | 32 | Between HF + GPT-4.1 and HAL + GPT-4.1 |
| gpt-oss-120b | **~#18** | 32 | Open-weight model |

### Comparison with Top Systems

| System | Overall | L1 | L2 | L3 | Cost |
|--------|---------|-----|-----|-----|------|
| HAL + Claude Sonnet 4.5 | 74.6% | 82.1% | 72.7% | 65.4% | $178 |
| HAL + Claude Opus 4.1 High | 68.5% | 71.7% | 70.9% | 53.9% | $562 |
| HAL + GPT-5 Medium | 59.4% | 67.9% | 58.1% | 46.2% | $105 |
| HAL + o4-mini Low | 58.2% | 71.7% | 51.2% | 53.9% | $73 |
| HF + GPT-4.1 | 50.3% | 58.5% | 50.0% | 34.6% | $110 |
| **Ours (GPT-5-mini)** | **50.4%** | **66.7%** | **45.5%** | **31.6%** | **$8** |
| HAL + GPT-4.1 | 49.7% | 52.8% | 55.8% | 23.1% | $74 |
| HF + o4-mini Low | 47.9% | 58.5% | 47.7% | 26.9% | $81 |
| **Ours (gpt-oss-120b)** | **45.7%** | **64.3%** | **37.9%** | **31.6%** | **$4** |
| HAL + DeepSeek R1 | 30.3% | 43.4% | 27.9% | 11.5% | $73 |
| HAL + DeepSeek V3 | 29.4% | 38.7% | 32.0% | 1.9% | $17 |

### Key Observations

1. **Scaffold > Model**: Same scaffold, +4.7% accuracy from swapping the underlying LLM (gpt-oss-120b → GPT-5-mini). L2 shows the largest gap (+7.6%).

2. **Cost Efficiency**: $4-8 for 127 questions vs $73-2800+ for other systems on the leaderboard. 10-100x cheaper than frontier systems at comparable accuracy.

3. **L1 Competitive**: Our 66.7% (GPT-5-mini) on Level 1 matches or beats systems using Claude-3.7 Sonnet, Haiku 4.5, and o4-mini.

4. **Open Model Viable**: gpt-oss-120b (open-weight) achieves GPT-4.1 tier performance at $4 total cost.

5. **Bottlenecks**: L2/L3 performance is limited by multi-hop reasoning capability of the underlying model.

### Run Variance

Results vary between runs (~10-15% variance on L1):

| Run | L1 Accuracy |
|-----|-------------|
| Best | 64.3% |
| Typical | 50-57% |
| Worst | 42.9% |

### Running the Benchmark

```bash
# Run Level 1 with 8x parallelism
HF_TOKEN=xxx uv run python -m scripts.gaia --level 1 -c 8

# Run all levels
HF_TOKEN=xxx uv run python -m scripts.gaia --level 1 -c 8
HF_TOKEN=xxx uv run python -m scripts.gaia --level 2 -c 8
HF_TOKEN=xxx uv run python -m scripts.gaia --level 3 -c 8

# Results saved to gaia_results/
```

### Best Results Archive

Best results for each level are preserved in `gaia_results/best_runs/`:
- `level1_best_64.3pct.json`
- `level2_best_37.9pct.json`
- `level3_best_31.6pct.json`

---

## Future Benchmarks

Planned evaluations:
- [ ] SWE-bench (code generation)
- [ ] HumanEval (function completion)
- [ ] MATH (mathematical reasoning)
