# CLAUDE.md — Vipin Lab

Autonomous research system. Phenomenon-driven. Kill-first. Evidence-gated.

## Quick Start

```bash
cd D:\research\vipin-lab
pip install -e .
cp .env.example .env   # add ANTHROPIC_API_KEY

vlab discover "LLM4Rec"                          # discover phenomena → ideas
vlab extend "LLM4Rec" --method "..." --limits "..."  # extend existing project
vlab transfer "conformal prediction" "LLM4Rec"   # cross-domain transfer
vlab pipeline <idea_id>                          # run full pipeline
vlab resume <idea_id>                            # resume after experiments
vlab ideas                                       # list all ideas
vlab sessions                                    # list sessions
vlab status                                      # check API keys
```

## Architecture

```
lab/
  core/
    models.py          — all data types (Idea, Phenomenon, DomainAnalogy, Paper, ...)
    config.py          — model lineup, quality thresholds
    orchestrator.py    — full pipeline, discovery modes, resume logic
  engines/
    phenomenon.py      — scans literature for anomalies (NOT keywords)
    analogy.py         — structural cross-domain transfer
    kill_first.py      — adversarial idea evaluation (auditor attacks, architect defends)
    evidence.py        — ARIS evidence labels (paper_result/official/diagnostic/pilot)
  phases/
    p1_ideation.py     — idea generation (phenomenon/extension/transfer)
    p2_refine.py       — research refine (stress test, feasibility)
    p3_experiment_plan.py — experiment design (blocks, gates, ≥8 baselines)
    p4_bridge.py       — experiment bridge (code skeleton, M0 sanity)
    p5_paper_write.py  — paper writing (evidence-backed)
    p6_review.py       — auto-review loop (Reviewer 1 + Adversary + Author)
    p7_p8_audit.py     — citation + claim audit (final gates)
  providers/
    llm.py             — LLM routing (Anthropic/OpenAI/OpenRouter), retries
    literature.py      — Semantic Scholar + arXiv search
  workspace/
    manager.py         — workspace lifecycle, idea/plan/paper serialization, resume
  memory/
    store.py           — cross-session learning (kill patterns, domain lessons)
  novelty/
    checker.py         — formal duplicate detection vs Semantic Scholar
  results/
    loader.py          — reads experiment outputs back into pipeline
  search/
    beam_search.py     — beam search over hypothesis space (inspired by BFTS)
cli/
  main.py              — vlab CLI (discover, extend, transfer, pipeline, resume, ideas)
workspace/             — session outputs (gitignored)
  .memory/             — cross-session memory (gitignored)
  <session_id>/        — session workspace
  ideas/<idea_id>/     — idea workspace
    idea.json          — idea state
    plan.json          — experiment plan
    paper.json         — paper state
    RESEARCH_QUESTION.md
    LITERATURE_STRESS_TEST.md
    FEASIBILITY.md
    EXPERIMENT_PLAN.md
    EXPERIMENT_TRACKER.md
    experiments/       — generated code skeleton
    papers/            — paper drafts, review logs, audit reports
```

## Pipeline Phases

```
discover/extend/transfer
    → kill-first (auditor attacks, architect defends)
    → research-refine (literature stress test, feasibility)
    → experiment-plan (5-7 blocks, ≥8 baselines, kill conditions)
    → experiment-bridge (code skeleton, M0 sanity script)
    ← USER RUNS EXPERIMENTS HERE →
    → paper-write (evidence-backed, claim-evidence map)
    → auto-review (Reviewer 1 + Adversary + Author, max 3 iterations)
    → citation-audit (completeness, fairness, recency)
    → claim-audit (empirical, novelty, theoretical, overclaims)
```

## Quality Gates

All gates use cross-model review (auditor ≠ executor):

| Gate | Threshold | Blocks |
|------|-----------|--------|
| Kill-first | novelty ≥6, feasibility ≥6 | Idea proceeds |
| Experiment plan | Evidence ≥6, Rigor ≥6, Gates ≥6, Feasibility ≥6, Paper-potential ≥6 | Phase 4 |
| Auto-review | all dimensions ≥7 | Paper proceeds |
| Claim audit | no blocking issues | Paper ready |

## Evidence Labels (ARIS)

| Label | Criteria | Use |
|-------|----------|-----|
| paper_result | ≥20 seeds, p<0.05, ≥8 baselines, fair | Main paper |
| official | full seeds, needs one check | Almost |
| diagnostic | 3-19 seeds OR missing stats | Supplementary |
| pilot | <3 seeds | Never in paper |

## Model Roles

| Model | Role | Used For |
|-------|------|----------|
| Claude Opus 4.7 | architect | Phenomenon analysis, kill arguments, analogical reasoning |
| Claude Sonnet 4.6 | executor | Experiment planning, paper writing, code generation |
| Claude Sonnet 4.5 | auditor | Cross-model review, experiment audit, claim audit |
| Claude Haiku 4.5 | screener | Fast pre-screening, literature triage |

**Critical rule**: auditor is always a different model from executor.

## Pipeline Resume

The pipeline pauses after Phase 4 (experiment-bridge) waiting for experiment results.

After running experiments:
1. Place results in `workspace/ideas/<idea_id>/experiments/results/`
2. Format: `block_<N>.json` with keys: `seeds_used`, `p_value`, `baselines`, `fair_comparison`, plus metric values
3. Run: `vlab resume <idea_id>`

## Isolation

This system:
- Reads no other project files
- Touches no servers or processes
- Has no shared state with Pony/TGL-Rec/TRUCE-Rec/CSATG-EDA
- All outputs go to `D:\research\vipin-lab\workspace\` (gitignored)

## Common Issues

**"No phenomena found"**: Semantic Scholar may be rate-limiting. Add `SEMANTIC_SCHOLAR_API_KEY` to `.env`.

**"Kill-first killed all ideas"**: Normal for first run. The beam search generates more diverse hypotheses. Try `vlab discover --no-beam` for single-pass mode.

**"Pipeline paused at bridge_done"**: Expected. Run experiments in `workspace/ideas/<id>/experiments/` then `vlab resume <id>`.

**Import errors**: Run `pip install -e .` from project root.
