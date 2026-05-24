"""
Domain-specific configuration.

Different research domains need different defaults:
- LLM4Rec: specific baselines (LLM2Rec, RLMRec, etc.), metrics (HR@K, NDCG@K)
- NLP: different baselines, BLEU/ROUGE metrics
- CV: ImageNet baselines, accuracy/mAP metrics
- General ML: flexible

DomainConfig overrides LabConfig defaults for a specific domain.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .config import LabConfig


@dataclass
class DomainConfig:
    """Domain-specific overrides for LabConfig."""
    name: str
    canonical_baselines: list[str] = field(default_factory=list)
    canonical_metrics: list[str] = field(default_factory=list)
    canonical_datasets: list[str] = field(default_factory=list)
    venue_targets: list[str] = field(default_factory=list)
    min_baselines_override: int | None = None
    phenomenon_keywords: list[str] = field(default_factory=list)  # domain-specific anomaly keywords


# Pre-configured domains
DOMAIN_CONFIGS: dict[str, DomainConfig] = {
    "llm4rec": DomainConfig(
        name="LLM4Rec",
        canonical_baselines=[
            "LLM2Rec", "LLM-ESR", "LLMEmb", "RLMRec", "IRLLRec",
            "ELMRec", "ProEx", "ProMax", "BIGRec", "TALLRec",
        ],
        canonical_metrics=["HR@5", "HR@10", "HR@20", "NDCG@5", "NDCG@10", "NDCG@20", "MRR"],
        canonical_datasets=["Amazon-Beauty", "Amazon-Books", "Amazon-Electronics", "Amazon-Movies"],
        venue_targets=["RecSys", "WWW", "SIGIR", "KDD", "NeurIPS"],
        min_baselines_override=8,
        phenomenon_keywords=[
            "calibration", "popularity bias", "cold start", "position bias",
            "hallucination", "ranking degradation", "coverage", "diversity",
        ],
    ),
    "nlp": DomainConfig(
        name="NLP",
        canonical_baselines=["BERT", "RoBERTa", "GPT-2", "T5", "BART", "LLaMA"],
        canonical_metrics=["BLEU", "ROUGE-L", "BERTScore", "Accuracy", "F1"],
        canonical_datasets=["GLUE", "SuperGLUE", "SQuAD", "CNN/DailyMail"],
        venue_targets=["ACL", "EMNLP", "NAACL", "NeurIPS", "ICLR"],
        phenomenon_keywords=[
            "hallucination", "factuality", "calibration", "length bias",
            "position bias", "in-context learning", "chain-of-thought",
        ],
    ),
    "cv": DomainConfig(
        name="Computer Vision",
        canonical_baselines=["ResNet-50", "ViT-B/16", "CLIP", "DINO", "MAE"],
        canonical_metrics=["Top-1 Accuracy", "mAP", "FID", "LPIPS"],
        canonical_datasets=["ImageNet", "COCO", "ADE20K", "Cityscapes"],
        venue_targets=["CVPR", "ICCV", "ECCV", "NeurIPS", "ICLR"],
        phenomenon_keywords=[
            "distribution shift", "adversarial robustness", "long-tail",
            "few-shot", "zero-shot", "spurious correlation",
        ],
    ),
    "ml": DomainConfig(
        name="Machine Learning",
        canonical_baselines=["XGBoost", "LightGBM", "Random Forest", "MLP", "Linear"],
        canonical_metrics=["Accuracy", "AUC-ROC", "F1", "MSE", "MAE"],
        canonical_datasets=["UCI", "Kaggle", "OpenML"],
        venue_targets=["NeurIPS", "ICML", "ICLR", "AISTATS"],
        phenomenon_keywords=[
            "overfitting", "generalization", "calibration", "uncertainty",
            "distribution shift", "label noise", "class imbalance",
        ],
    ),
}


def get_domain_config(domain: str) -> DomainConfig | None:
    """Get domain config by fuzzy name match."""
    domain_lower = domain.lower()
    # Exact match
    if domain_lower in DOMAIN_CONFIGS:
        return DOMAIN_CONFIGS[domain_lower]
    # Fuzzy match
    for key, cfg in DOMAIN_CONFIGS.items():
        if key in domain_lower or domain_lower in key or cfg.name.lower() in domain_lower:
            return cfg
    return None


def apply_domain_config(lab_config: LabConfig, domain: str) -> tuple[LabConfig, DomainConfig | None]:
    """Apply domain-specific overrides to LabConfig. Returns (updated_config, domain_config)."""
    domain_cfg = get_domain_config(domain)
    if domain_cfg is None:
        return lab_config, None
    if domain_cfg.min_baselines_override is not None:
        lab_config.min_baselines = domain_cfg.min_baselines_override
    return lab_config, domain_cfg
