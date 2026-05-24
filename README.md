# Vipin Lab

**Autonomous research system. Phenomenon-driven. Kill-first. Evidence-gated.**

Not another keyword-to-paper pipeline. Vipin Lab starts from observed anomalies in the literature, stress-tests every idea with adversarial review before writing a single line of code, and enforces ARIS evidence discipline throughout.

---

## The Problem With Existing Systems

Every major auto-research system (AI Scientist, AgentLaboratory, AI-Researcher) follows the same pattern:

```
keyword → brainstorm ideas → run experiments → write paper
```

This produces papers that score high on novelty metrics but have **negative correlation with real-world impact** (ρ = −0.29, IdeaBench 2024). The systems optimize for the appearance of novelty, not scientific contribution.

Three root causes:
1. **Method-driven, not phenomenon-driven** — ideas start from "what method can I apply?" not "what anomaly did I observe?"
2. **No adversarial gate** — ideas are validated, not attacked. Nobody writes the strongest rejection argument first.
3. **No evidence discipline** — all results are treated equally. A 3-seed pilot and a 20-seed paper result look the same.

---

## What Vipin Lab Does Differently

### 1. Phenomenon Observatory

Instead of starting from keywords, the system scans the literature for **anomalies, contradictions, and unexplained results**:

- "LLM recommenders consistently underperform at rank positions > 5 despite theoretical guarantees"
- "Metric A and Metric B diverge in domain Z — models that rank well on A rank poorly on B"
- "Technique X works in domain A but fails in domain B despite similar structure"

Every idea starts from a phenomenon. No phenomenon → no idea.

### 2. Kill-First Ideation

Before any code is written, the system writes the **strongest possible rejection argument** for every idea:

1. **Kill argument** (auditor model, different from idea generator): prior work kill, theoretical kill, empirical kill, scope kill, novelty kill
2. **Rebuttal** (architect model): why the idea survives despite the kill argument
3. **Novelty + feasibility scoring**: both must be ≥6/10 to proceed

Ideas that die in round 1 save months of wasted work.

### 3. Analogical Bridge

Cross-domain transfer via **structural analogy**, not graph traversal:

- Analyzes the source method's structural role (what fundamental problem does it solve?)
- Searches for the same structural problem in the target domain
- Identifies what needs to change for the transfer to work
- Scores analogy confidence

Example: conformal prediction provides coverage guarantees on set-valued outputs in NLP. LLM recommenders produce ranked lists with uncalibrated confidence. Structural analogy: both involve set-valued outputs with coverage requirements. Transfer: apply conformal prediction to recommendation depth.

### 4. Evidence Gate (ARIS discipline)

Every result is labeled. Only `paper_result` evidence goes in the paper:

| Label | Criteria | Use |
|-------|----------|-----|
| `paper_result` | ≥20 seeds, paired t-test p<0.05, ≥8 baselines, fair comparison | Main paper |
| `official` | Full seeds, needs one more check | Almost |
| `diagnostic` | 3-19 seeds OR missing statistical test | Supplementary only |
| `pilot` | <3 seeds OR no statistical test | Never in paper |

The evidence gate blocks paper claims that lack `paper_result` evidence.

### 5. Cross-Model Audit Gates

Different agents review each other's work at every gate:

- **Kill-first**: auditor model attacks, architect model defends
- **Experiment plan audit**: auditor scores Evidence, Rigor, Gates, Feasibility, Paper-potential (all ≥6)
- **Auto-review loop**: auditor as Reviewer 1, architect as Adversary, executor as author
- **Claim audit**: auditor audits claims written by executor

---

## Pipeline

```
Domain / Project / Source Domain
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  DISCOVERY                                                   │
│                                                              │
│  Phenomenon Observatory ──→ Idea Generator                  │
│  Analogical Bridge      ──→ Idea Generator                  │
│  Extension Engine       ──→ Idea Generator                  │
│                                                              │
│  Kill-First Engine ──→ [GATE: novelty ≥6, feasibility ≥6]  │
└─────────────────────────────────────────────────────────────┘
         │ surviving ideas
         ▼
┌─────────────────────────────────────────────────────────────┐
│  RESEARCH REFINE                                             │
│                                                              │
│  Atomic claim decomposition                                  │
│  Literature stress test (3 closest papers + kill argument)  │
│  Feasibility assessment (data, compute, baselines, risks)   │
│                                                              │
│  [GATE: literature verdict ≠ killed, feasibility ≥6]       │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  EXPERIMENT PLAN                                             │
│                                                              │
│  5-7 blocks with falsifiable hypotheses                      │
│  ≥8 baselines, ≥20 seeds, concrete kill conditions          │
│  Milestone gates (M0, M1, M2)                               │
│                                                              │
│  [GATE: Evidence ≥6, Rigor ≥6, Gates ≥6, Feasibility ≥6]  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  EXPERIMENT BRIDGE                                           │
│                                                              │
│  Config-driven runner architecture                           │
│  Baseline wrappers + method skeleton                         │
│  M0 sanity check script                                      │
│                                                              │
│  ← USER RUNS EXPERIMENTS HERE (local or server) →          │
└─────────────────────────────────────────────────────────────┘
         │ results
         ▼
┌─────────────────────────────────────────────────────────────┐
│  PAPER WRITE + AUDIT                                         │
│                                                              │
│  Evidence-backed narrative (every claim has paper_result)   │
│  Auto-review loop (Reviewer 1 + Adversary + Author)         │
│  Citation audit (completeness, fairness, recency)           │
│  Claim audit (empirical, novelty, theoretical, overclaims)  │
│                                                              │
│  [GATE: all review scores ≥7, no blocking issues]          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
    Paper ready for submission
```

---

## Quick Start

```bash
cd D:\research\vipin-lab
pip install -e .
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env

# Discover phenomena and ideas in a domain
vlab discover "LLM4Rec"

# Extend an existing project
vlab extend "LLM4Rec" \
  --method "conformal prediction for recommendation depth" \
  --results "HR@10=0.42, NDCG@10=0.31" \
  --limits "only tested on Amazon datasets"

# Cross-domain transfer
vlab transfer "conformal prediction" "LLM4Rec"

# Run full pipeline on a surviving idea
vlab pipeline <idea_id>

# Session management
vlab sessions
vlab show <session_id>
vlab status
```

---

## Architecture

```
vipin-lab/
├── lab/
│   ├── core/
│   │   ├── models.py          # All data types: Idea, Phenomenon, DomainAnalogy, Paper, ...
│   │   ├── config.py          # Model lineup, quality thresholds, API keys
│   │   └── orchestrator.py    # Full pipeline orchestration
│   ├── engines/
│   │   ├── phenomenon.py      # Phenomenon Observatory — scan for anomalies
│   │   ├── analogy.py         # Analogical Bridge — cross-domain transfer
│   │   ├── kill_first.py      # Kill-First Engine — adversarial idea evaluation
│   │   └── evidence.py        # Evidence Gate — ARIS evidence discipline
│   ├── phases/
│   │   ├── p1_ideation.py     # Idea generation (phenomenon/extension/transfer)
│   │   ├── p2_refine.py       # Research refine (stress test, feasibility)
│   │   ├── p3_experiment_plan.py  # Experiment design (blocks, gates, baselines)
│   │   ├── p4_bridge.py       # Experiment bridge (code skeleton)
│   │   ├── p5_paper_write.py  # Paper writing (evidence-backed)
│   │   ├── p6_review.py       # Auto-review loop (multi-agent)
│   │   └── p7_p8_audit.py     # Citation + claim audit (final gates)
│   └── providers/
│       ├── llm.py             # LLM routing (Anthropic, OpenAI, OpenRouter)
│       └── literature.py      # Semantic Scholar + arXiv search
├── cli/
│   └── main.py                # vlab CLI (discover, extend, transfer, pipeline)
├── workspace/                 # Session outputs (gitignored)
├── pyproject.toml
└── .env.example
```

---

## Model Lineup

| Model | Role | Used For |
|-------|------|----------|
| Claude Opus 4.7 | Architect | Phenomenon analysis, kill arguments, analogical reasoning |
| Claude Sonnet 4.6 | Executor | Experiment planning, paper writing, code generation |
| Claude Sonnet 4.5 | Auditor | Cross-model review, experiment audit, claim audit |
| Claude Haiku 4.5 | Screener | Fast pre-screening, literature triage |

The auditor is always a different model from the executor. This is the key to avoiding self-review bias.

---

## Comparison

| Feature | AI Scientist v2 | AgentLaboratory | AI-Researcher | **Vipin Lab** |
|---------|:--------------:|:---------------:|:-------------:|:-------------:|
| Phenomenon-driven discovery | ✗ | ✗ | ✗ | **✓** |
| Kill-first adversarial gate | ✗ | ✗ | ✗ | **✓** |
| Cross-domain analogical transfer | ✗ | ✗ | ✗ | **✓** |
| Evidence labels (paper_result/diagnostic) | ✗ | ✗ | ✗ | **✓** |
| Cross-model audit gates | Partial | ✗ | Partial | **✓** |
| Experiment blocks with kill conditions | ✗ | ✗ | ✗ | **✓** |
| Fairness enforcement | ✗ | ✗ | ✗ | **✓** |
| Claim-evidence map | ✗ | ✗ | ✗ | **✓** |
| Adversary in review loop | ✗ | ✗ | ✗ | **✓** |
| Isolation from other projects | N/A | N/A | N/A | **✓** |

---

## Design Principles

1. **Phenomenon-first, not method-first** — every idea starts from an observed anomaly
2. **Kill before you build** — write the strongest rejection argument before any code
3. **Evidence discipline** — label every result, only paper_result goes in the paper
4. **Cross-model review** — different agents audit each other's work
5. **Fairness enforcement** — same data, preprocessing, compute, tuning for all baselines
6. **Reproducibility-first** — config-driven, seed-controlled, gitignored results
7. **Isolation** — this lab does not touch any other project's files, servers, or processes

---

## License

MIT
