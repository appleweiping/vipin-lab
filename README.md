<div align="center">

<img src="banner.png" alt="Vipin Lab" width="720" />

# ⚗ Vipin Lab

### Autonomous Research System — Phenomenon-Driven · Kill-First · Evidence-Gated

[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-ruff-orange?style=flat-square)](https://github.com/astral-sh/ruff)

**Not another keyword-to-paper pipeline.**

Vipin Lab starts from observed anomalies in the literature, stress-tests every idea with adversarial review before writing a single line of code, and enforces ARIS evidence discipline throughout — with hard guards against toy-ification and idea generation death loops.

</div>

---

## The Problem With Every Existing System

Every major auto-research system (AI Scientist, AgentLaboratory, AI-Researcher) follows the same pattern:

```
keyword → brainstorm ideas → run experiments → write paper
```

This produces three failure modes that no existing system addresses:

**1. Idea generation death loops.** LLM generates idea → self-checks → finds prior work → generates surface variation → finds prior work again → repeat. Consumes tokens, produces nothing. The system optimizes for the *appearance* of novelty, not actual novelty. IdeaBench (2024) confirmed: LLM novelty scores negatively correlate with real-world impact (ρ = −0.29).

**2. Toy-ification.** Systems default to small datasets, weak baselines, toy metrics, or invent "environment constraints" to avoid hard experiments. A 3-seed pilot gets treated the same as a 20-seed paper result.

**3. Method-driven, not phenomenon-driven.** Ideas start from "what method can I apply?" not "what anomaly did I observe?" This produces stitching (A + B), not discovery.

Vipin Lab solves all three at the architecture level.

---

## What's Different

### Phenomenon Observatory
Instead of starting from keywords, the system scans the literature for **anomalies, contradictions, and unexplained results**:
- "LLM recommenders consistently underperform at rank positions > 5 despite theoretical guarantees"
- "Metric A and Metric B diverge in domain Z — models that rank well on A rank poorly on B"
- "Technique X works in domain A but fails in domain B despite similar structure"

Every idea starts from a phenomenon. No phenomenon → no idea.

### Kill-First Ideation
Before any code is written, the system writes the **strongest possible rejection argument** for every idea. Auditor model attacks. Architect model defends. Ideas that die in round 1 save months of wasted work.

### Death Loop Prevention
When an idea is killed by prior work, the system **forces structural divergence** — not a surface variation. Word overlap > 60% with a previously killed idea → rejected immediately. The divergence engine generates a fundamentally different direction, not "the same idea with a different dataset."

### Anti-Toy Enforcement
Hard-coded minimum standards that cannot be overridden by LLM output:
- ≥ 8 baselines (state-of-the-art, not weak ones)
- ≥ 20 seeds for paper results
- ≥ 3 metrics reported
- Standard benchmarks required
- Environment excuses blocked ("due to compute constraints" → rejected)

### Analogical Bridge
Cross-domain transfer via **structural analogy**, not graph traversal. Analyzes why a method works in domain A, then asks whether the same structural problem exists in domain B. Scores analogy confidence. Generates transfer ideas only when the analogy is strong.

### Evidence Gate (ARIS Discipline)
Every result is labeled. Only `paper_result` evidence goes in the paper:

| Label | Criteria | Use |
|-------|----------|-----|
| `paper_result` | ≥20 seeds, p<0.05, ≥8 baselines, fair comparison | Main paper |
| `official` | Full seeds, needs one check | Almost |
| `diagnostic` | 3-19 seeds OR missing stats | Supplementary only |
| `pilot` | <3 seeds | Never in paper |

### Cross-Model Audit Gates
Different agents review each other's work at every gate. Auditor ≠ Executor. This is the key to avoiding self-review bias.

---

## Architecture

```
Domain / Project / Source Domain
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DISCOVERY ENGINE                                                    │
│                                                                      │
│  Phenomenon Observatory ──→ Beam Search ──→ Idea Generator         │
│  Analogical Bridge      ──→ Idea Generator                          │
│  Extension Engine       ──→ Idea Generator                          │
│                                                                      │
│  Novelty Checker ──→ [GATE: not a duplicate]                        │
│  Kill-First Engine ──→ [GATE: novelty ≥6, feasibility ≥6]          │
│  Death Loop Guard ──→ [GATE: not a surface variation]               │
└─────────────────────────────────────────────────────────────────────┘
         │ surviving ideas
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  RESEARCH REFINE                                                     │
│                                                                      │
│  Atomic claim decomposition                                          │
│  Literature stress test (3 closest papers + kill argument)          │
│  Feasibility assessment (data, compute, baselines, risks)           │
│                                                                      │
│  [GATE: literature verdict ≠ killed, feasibility ≥6]               │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  EXPERIMENT PLAN                                                     │
│                                                                      │
│  5-7 blocks with falsifiable hypotheses                              │
│  ≥8 baselines, ≥20 seeds, concrete kill conditions                  │
│  Anti-toy audit (static + LLM) → hard minimum enforcement           │
│                                                                      │
│  [GATE: Evidence ≥6, Rigor ≥6, Gates ≥6, Feasibility ≥6]          │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  EXPERIMENT BRIDGE                                                   │
│                                                                      │
│  Config-driven runner architecture                                   │
│  Baseline wrappers + method skeleton                                 │
│  M0 sanity check script                                              │
│                                                                      │
│  ← USER RUNS EXPERIMENTS HERE (local or server) →                  │
└─────────────────────────────────────────────────────────────────────┘
         │ results
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PAPER WRITE + AUDIT                                                 │
│                                                                      │
│  Evidence-backed narrative (every claim has paper_result)           │
│  Auto-review loop (Reviewer 1 + Adversary + Author, max 3 iter)    │
│  Citation audit (completeness, fairness, recency)                   │
│  Claim audit (empirical, novelty, theoretical, overclaims)          │
│                                                                      │
│  [GATE: all review scores ≥7, no blocking issues]                  │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
    Paper ready for submission
```

### Integrated Algorithms

| Algorithm | Source | What It Does |
|-----------|--------|-------------|
| Phenomenon Observatory | Novel | Scans literature for anomalies, not keywords |
| Kill-First Ideation | Novel | Adversarial evaluation before any code |
| Death Loop Prevention | Novel | Structural divergence forcing on repeated kills |
| Anti-Toy Enforcement | Novel | Hard minimum standards, environment excuse blocking |
| Analogical Bridge | Novel | Structural cross-domain transfer (not graph traversal) |
| Beam Search | AI Scientist v2 (BFTS) | Explores hypothesis space in parallel |
| Self-Refine | Madaan et al. 2023 | Iterative critique-and-improve loop |
| Evidence Labels | ARIS | paper_result / official / diagnostic / pilot |
| Cross-Model Audit | ARIS | Auditor ≠ Executor at every gate |
| Tool-Augmented Agents | AI-Researcher | Web search, Semantic Scholar, file I/O |

---

## Quick Start

```bash
git clone https://github.com/appleweiping/vipin-lab
cd vipin-lab
make install          # pip install -e ".[dev]" + copy .env.example
# Add ANTHROPIC_API_KEY to .env

vlab status           # verify configuration
vlab discover "LLM4Rec"                          # phenomenon → ideas
vlab extend "LLM4Rec" --method "..." --limits "..."  # extend existing project
vlab transfer "conformal prediction" "LLM4Rec"   # cross-domain transfer
vlab pipeline <idea_id>                          # run full pipeline
vlab resume <idea_id>                            # resume after experiments
vlab ideas                                       # list all ideas
```

---

## CLI Reference

```
vlab discover <domain>              Scan domain for phenomena → generate ideas
vlab extend <domain>                Generate follow-up ideas from existing project
  --method "..."                    Current method description
  --results "..."                   Current results summary
  --limits "..."                    Known limitations
vlab transfer <source> <target>     Cross-domain analogical transfer
vlab pipeline <idea_id>             Run full pipeline on a surviving idea
vlab resume <idea_id>               Resume pipeline after running experiments
vlab ideas [--domain X] [--status Y]  List all ideas
vlab sessions                       List recent sessions
vlab show <session_id>              Show session details
vlab status                         Check API key configuration
```

---

## Pipeline Resume

The pipeline pauses after Phase 4 (experiment-bridge) waiting for experiment results.

```bash
# After running experiments, place results in:
workspace/ideas/<idea_id>/experiments/results/block_<N>.json

# Each result file format:
{
  "seeds_used": 20,
  "p_value": 0.003,
  "baselines": {"LLM2Rec": 0.41, "RLMRec": 0.38, ...},
  "fair_comparison": true,
  "HR@10": 0.47,
  "NDCG@10": 0.33
}

# Then resume:
vlab resume <idea_id>
```

---

## Model Lineup

| Agent | Model | Role | Used For |
|-------|-------|------|----------|
| Opus | Claude Opus 4.7 | Architect | Phenomenon analysis, kill arguments, analogical reasoning |
| Sonnet | Claude Sonnet 4.6 | Executor | Experiment planning, paper writing, code generation |
| Auditor | Claude Sonnet 4.5 | Auditor | Cross-model review, experiment audit, claim audit |
| Haiku | Claude Haiku 4.5 | Screener | Fast pre-screening, literature triage |

**Critical rule**: Auditor is always a different model from Executor.

---

## Domain Support

Pre-configured domains with canonical baselines, metrics, and datasets:

| Domain | Baselines | Metrics | Datasets |
|--------|-----------|---------|----------|
| LLM4Rec | LLM2Rec, RLMRec, IRLLRec, ELMRec, ProEx, ProMax, BIGRec, TALLRec | HR@K, NDCG@K, MRR | Amazon-Beauty/Books/Electronics/Movies |
| NLP | BERT, RoBERTa, GPT-2, T5, BART, LLaMA | BLEU, ROUGE-L, BERTScore, F1 | GLUE, SuperGLUE, SQuAD |
| CV | ResNet-50, ViT-B/16, CLIP, DINO, MAE | Top-1 Acc, mAP, FID | ImageNet, COCO |
| ML | XGBoost, LightGBM, Random Forest, MLP | AUC-ROC, F1, MSE | UCI, OpenML |

---

## Project Structure

```
vipin-lab/
├── lab/
│   ├── core/
│   │   ├── models.py          # All data types: Idea, Phenomenon, DomainAnalogy, Paper
│   │   ├── config.py          # Model lineup, quality thresholds
│   │   ├── orchestrator.py    # Full pipeline, discovery modes, resume logic
│   │   ├── domain_config.py   # Domain-specific baselines, metrics, datasets
│   │   └── progress.py        # Streaming progress reporter
│   ├── engines/
│   │   ├── phenomenon.py      # Phenomenon Observatory — scan for anomalies
│   │   ├── analogy.py         # Analogical Bridge — structural cross-domain transfer
│   │   ├── kill_first.py      # Kill-First Engine — adversarial idea evaluation
│   │   ├── evidence.py        # Evidence Gate — ARIS evidence labels
│   │   └── anti_toy.py        # Anti-Toy Engine — death loop prevention + toy blocking
│   ├── phases/
│   │   ├── p1_ideation.py     # Idea generation (phenomenon/extension/transfer)
│   │   ├── p2_refine.py       # Research refine (stress test, feasibility)
│   │   ├── p3_experiment_plan.py  # Experiment design (blocks, gates, baselines)
│   │   ├── p4_bridge.py       # Experiment bridge (code skeleton, M0 sanity)
│   │   ├── p5_paper_write.py  # Paper writing (evidence-backed)
│   │   ├── p6_review.py       # Auto-review loop (Reviewer 1 + Adversary + Author)
│   │   └── p7_p8_audit.py     # Citation + claim audit (final gates)
│   ├── tools/
│   │   ├── registry.py        # Tool registry (web search, Semantic Scholar, file I/O)
│   │   └── agent.py           # Tool-augmented agent (tool-call → result → continue)
│   ├── search/
│   │   └── beam_search.py     # Beam search over hypothesis space
│   ├── workspace/
│   │   └── manager.py         # Workspace lifecycle, serialization, pipeline resume
│   ├── memory/
│   │   └── store.py           # Cross-session learning (kill patterns, domain lessons)
│   ├── novelty/
│   │   └── checker.py         # Formal duplicate detection vs Semantic Scholar
│   ├── results/
│   │   └── loader.py          # Reads experiment outputs back into pipeline
│   └── providers/
│       ├── llm.py             # LLM routing (Anthropic/OpenAI/OpenRouter)
│       └── literature.py      # Semantic Scholar + arXiv search
├── cli/
│   └── main.py                # vlab CLI
├── tests/
│   └── test_core.py           # 18 unit tests
├── workspace/                 # Session outputs (gitignored)
├── Makefile
├── pyproject.toml
├── CLAUDE.md
└── .env.example
```

---

## Comparison

| Feature | AI Scientist v2 | AgentLaboratory | AI-Researcher | **Vipin Lab** |
|---------|:--------------:|:---------------:|:-------------:|:-------------:|
| Phenomenon-driven discovery | ✗ | ✗ | ✗ | **✓** |
| Kill-first adversarial gate | ✗ | ✗ | ✗ | **✓** |
| Death loop prevention | ✗ | ✗ | ✗ | **✓** |
| Anti-toy enforcement | ✗ | ✗ | ✗ | **✓** |
| Cross-domain analogical transfer | ✗ | ✗ | ✗ | **✓** |
| Evidence labels (paper_result/diagnostic) | ✗ | ✗ | ✗ | **✓** |
| Cross-model audit gates | Partial | ✗ | Partial | **✓** |
| Experiment blocks with kill conditions | ✗ | ✗ | ✗ | **✓** |
| Beam search over hypothesis space | ✓ (code) | ✗ | ✗ | **✓ (ideas)** |
| Tool-augmented agents | ✗ | ✗ | ✓ | **✓** |
| Cross-session memory | ✗ | ✓ | ✗ | **✓** |
| Pipeline resume after experiments | ✗ | ✗ | ✗ | **✓** |
| Domain-specific configuration | ✗ | ✗ | ✗ | **✓** |
| Test suite | ✗ | ✗ | ✗ | **✓** |

---

## Configuration

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...                    # optional
SEMANTIC_SCHOLAR_API_KEY=               # optional, increases rate limits
OPENROUTER_API_KEY=sk-or-...            # optional
```

```python
# backend/config.py — key thresholds
min_novelty_score: float = 6.0          # idea must score ≥6 to proceed
min_feasibility_score: float = 6.0
min_experiment_audit_score: float = 6.0  # all plan dimensions
min_review_score: float = 7.0           # auto-review-loop
min_baselines: int = 8                  # minimum baselines for paper results
min_seeds_paper: int = 20               # seeds for paper_result label
min_citations: int = 30                 # minimum citations for top venue
```

---

## Design Principles

1. **Phenomenon-first, not method-first** — every idea starts from an observed anomaly
2. **Kill before you build** — write the strongest rejection argument before any code
3. **No death loops** — structural divergence forced when ideas are killed by prior work
4. **No toy-ification** — hard minimum standards, environment excuses blocked
5. **Evidence discipline** — label every result, only paper_result goes in the paper
6. **Cross-model review** — different agents audit each other's work
7. **Fairness enforcement** — same data, preprocessing, compute, tuning for all baselines
8. **Reproducibility-first** — config-driven, seed-controlled, gitignored results
9. **Isolation** — this lab does not touch any other project's files, servers, or processes

---

## License

MIT
