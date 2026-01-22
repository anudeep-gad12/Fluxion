# Agent Reasoning & Search Improvement Research

> Research findings on improving LLM agent search and reasoning quality.
> Date: 2026-01-22

---

## Problem Statement

GAIA benchmark analysis shows ~90% of failures are **wrong answers**, not timeouts:
- Model constructs poor search queries
- Trusts first search result without verification
- Does mental math instead of using python_execute
- Misinterprets or conflates information from sources

---

## Research Findings

### 1. Chain of Verification (CoVe)

**Source:** [Meta AI - Chain-of-Verification Reduces Hallucination in LLMs](https://arxiv.org/abs/2309.11495)

**Impact:** Reduces hallucinations by **50-70%**

**Four-Step Process:**
1. **Generate Baseline Response** - Answer the question normally
2. **Plan Verifications** - Generate verification questions about the answer
3. **Execute Verifications** - Answer verification questions independently (without seeing original answer)
4. **Generate Final Response** - Revise based on inconsistencies found

**Best Variant:** "Factored" execution - each verification question answered independently without exposure to initial answer, preventing bias propagation.

**Limitations:**
- Adds latency (multiple LLM calls)
- Doesn't catch reasoning errors, only factual inaccuracies
- Still can produce incorrect information

---

### 2. Self-Consistency

**Source:** [State of LLMs 2025 - Sebastian Raschka](https://magazine.sebastianraschka.com/p/state-of-llms-2025)

**Technique:**
- Generate multiple independent reasoning chains for same question
- Select most common answer via majority voting
- Combined with self-refinement iterations improves accuracy

**2026 Trend:** Inference-time scaling - spending more compute at inference to improve quality. Self-consistency + self-refinement is a key pattern.

---

### 3. ReAct (Reasoning + Acting)

**Source:** [ReAct: Synergizing Reasoning and Acting in Language Models](https://react-lm.github.io/) (ICLR 2023, Top 5% Paper)

**Key Insight:** Interleave reasoning traces with tool actions, don't separate them.

**Performance:**
- Overcomes hallucination and error propagation on HotpotQA and Fever
- Outperforms imitation/RL methods by 34% on ALFWorld, 10% on WebShop

**Best Approach:** ReAct + Chain-of-Thought - uses both internal knowledge AND external information obtained during reasoning.

**Caveat:** [Recent research](https://arxiv.org/html/2405.13966v1) suggests performance may stem from exemplar-query similarity rather than true reasoning.

---

### 4. Multi-Source Verification

**Source:** [Survey of LLM-based Deep Search Agents](https://arxiv.org/html/2508.05668v3)

**Key Principles:**
- Search agents should "integrate information from diverse sources"
- Performance scales with number of allowed search actions
- "Active Fact-Checking" - verify factual consistency via external retrieval

**Combined Approach:** Integrate reasoning scaling + search scaling:
- Self-Consistency (SC)
- Best-of-N (BoN)
- Monte Carlo Tree Search (MCTS)

---

### 5. Self-Verification Prompting

**Source:** [Learn Prompting - Self-Verification](https://learnprompting.org/docs/advanced/self_criticism/self_verification)

**Two-Step Process:**
1. **Forward Reasoning** - Generate candidate answers with CoT prompting
2. **Backward Verification** - LLM validates its own answers for correctness

**Automated Consistency Analysis:**
- Execute repeated/paraphrased queries
- Score consistency using lexical similarity metrics (Jaccard, Cosine, Levenshtein)
- Flag inconsistent responses for review

---

## Practical Implementation

### Recommended System Prompt Additions

```
SEARCH & VERIFICATION PROTOCOL:

1. MULTIPLE SEARCHES: For factual questions, search at least twice with different
   query phrasings. Don't trust a single search result.

2. SOURCE AUTHORITY: Prefer authoritative sources in this order:
   - Official government sites (.gov)
   - Academic institutions (.edu)
   - Wikipedia (for general facts)
   - Established news organizations
   - Avoid: forums, blogs, paywalled content

3. CROSS-VERIFICATION: If sources disagree, search again to resolve.
   Note the disagreement in your reasoning.

4. MANDATORY PYTHON: For ANY calculation (math, dates, unit conversions,
   percentages), use python_execute. Never compute mentally.

5. SELF-CHECK: Before final answer, ask yourself:
   - "What evidence supports this answer?"
   - "Could I be confusing this with something similar?"
   - "Is there a more authoritative source I should check?"
```

### Implementation Options

| Option | Complexity | Impact | Notes |
|--------|------------|--------|-------|
| Enhanced system prompt | Low | Medium | Guidance only, model may ignore |
| CoVe in agent loop | High | High | Adds 3-4x latency per question |
| Multi-search requirement | Medium | Medium | Modify agent to require 2+ searches |
| Python-only calculations | Low | Medium | Already in prompt, needs enforcement |

---

## Metrics to Track

After implementing improvements:

1. **Search behavior:**
   - Avg searches per question
   - % questions with multiple source verification

2. **Calculation behavior:**
   - % calculations done via python_execute vs mental math

3. **Answer quality:**
   - GAIA accuracy by level
   - Wrong answer rate (should decrease)

---

## References

1. [Chain-of-Verification Reduces Hallucination in LLMs](https://arxiv.org/abs/2309.11495) - Meta AI, 2023
2. [ReAct: Synergizing Reasoning and Acting](https://react-lm.github.io/) - Google/Princeton, ICLR 2023
3. [State of LLMs 2025](https://magazine.sebastianraschka.com/p/state-of-llms-2025) - Sebastian Raschka
4. [Survey of LLM-based Deep Search Agents](https://arxiv.org/html/2508.05668v3) - 2025
5. [Self-Verification Prompting](https://learnprompting.org/docs/advanced/self_criticism/self_verification) - Learn Prompting
6. [On the Brittle Foundations of ReAct Prompting](https://arxiv.org/html/2405.13966v1) - 2024
7. [Agentic AI Trends 2026](https://machinelearningmastery.com/7-agentic-ai-trends-to-watch-in-2026/) - Machine Learning Mastery

---

## Next Steps

1. Review current agent system prompt (`orchestrator/agent/agent_engine.py`)
2. Add search/verification guidance based on research
3. Run GAIA benchmark to measure impact
4. Iterate based on results
