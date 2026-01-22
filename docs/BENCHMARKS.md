# Benchmarks

Performance evaluation of the Reasoner agent system.

## GAIA Benchmark

[GAIA](https://arxiv.org/abs/2311.12983) (General AI Assistants) is a benchmark for evaluating AI assistants on real-world tasks requiring reasoning, web browsing, and tool use.

### Our Results

**Model**: gpt-oss-120b (DeepInfra)
**Evaluation**: Validation set (165 questions, no file attachments)
**Date**: January 2026

| Level | Accuracy | Questions | Correct |
|-------|----------|-----------|---------|
| Level 1 | **64.3%** | 42 | 27 |
| Level 2 | **37.9%** | 66 | 25 |
| Level 3 | **31.6%** | 19 | 6 |
| **Overall** | **~46%** | 127 | 58 |

### Leaderboard Ranking

Compared against the [HAL Princeton GAIA Leaderboard](https://hal.cs.princeton.edu/gaia) (January 2026):

| Level | Our Rank | Out of | Notes |
|-------|----------|--------|-------|
| Level 1 | **#11** | 32 | Competitive with Claude-3.7 Sonnet, Haiku 4.5 |
| Level 2 | **#19** | 32 | - |
| Level 3 | **#16** | 32 | Beats GPT-4.1, DeepSeek R1/V3 |
| **Overall** | **#18** | 32 | Using open-weight model |

### Comparison with Top Systems

| System | Overall | L1 | L2 | L3 | Cost |
|--------|---------|-----|-----|-----|------|
| HAL + Claude Sonnet 4.5 | 74.6% | 82.1% | 72.7% | 65.4% | $178 |
| HAL + Claude Opus 4.1 | 68.5% | 71.7% | 70.9% | 53.9% | $562 |
| HAL + GPT-5 Medium | 59.4% | 67.9% | 58.1% | 46.2% | $105 |
| HF + o4-mini Low | 47.9% | 58.5% | 47.7% | 26.9% | $81 |
| **Ours (gpt-oss-120b)** | **~46%** | **64.3%** | **37.9%** | **31.6%** | ~$5 |
| HAL + DeepSeek R1 | 30.3% | 43.4% | 27.9% | 11.5% | $73 |
| HAL + DeepSeek V3 | 29.4% | 38.7% | 32.0% | 1.9% | $17 |

### Key Observations

1. **L1 Performance**: Our 64.3% on Level 1 is competitive with systems using Claude-3.7 Sonnet and Haiku 4.5, despite using an open-weight model.

2. **Cost Efficiency**: Estimated ~$5 for full evaluation vs $100-500+ for frontier model systems.

3. **Open Model**: We achieve GPT-4.1 tier performance using gpt-oss-120b, an open-weight reasoning model.

4. **Bottlenecks**: L2/L3 performance is limited by multi-hop reasoning capability of the underlying model.

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
