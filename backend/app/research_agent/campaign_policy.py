"""Versioned campaign authority. Snapshots never inherit later default changes."""
from typing import Literal

from pydantic import Field, model_validator

from .hypotheses import Strict


class CampaignBudget(Strict):
    wall_minutes: int = Field(default=1440, ge=1, le=10080, strict=True)
    simulations: int = Field(default=240, ge=1, le=2000, strict=True)
    hypotheses: int = Field(default=24, ge=1, le=200, strict=True)
    children: int = Field(default=12, ge=0, le=100, strict=True)
    families: int = Field(default=6, ge=1, le=30, strict=True)
    external_searches: int = Field(default=0, ge=0, le=100, strict=True)
    llm_calls: int = Field(default=60, ge=0, le=1000, strict=True)
    llm_usd: float = Field(default=10, ge=0, le=10000)
    compute_minutes: int = Field(default=720, ge=1, le=10080, strict=True)


class DatasetPolicy(Strict):
    # Counts refer to supplied completed market sessions, never inferred weekdays.
    warmup_sessions: int = Field(default=250, ge=1, le=2000, strict=True)
    min_development_sessions: int = Field(default=252, ge=2, le=5000, strict=True)
    min_holdout_sessions: int = Field(default=63, ge=1, le=2000, strict=True)
    development_percent: int = Field(default=70, ge=50, le=90, strict=True)
    internal_windows: int = Field(default=3, ge=2, le=10, strict=True)


class CampaignPolicy(Strict):
    version: Literal['research_campaign_policy_v1'] = 'research_campaign_policy_v1'
    symbols: list[str] = Field(default_factory=lambda: ['QQQ'], min_length=1, max_length=20)
    timeframes: list[Literal['1m', '5m', '15m', '30m', '1h', '4h', '1d']] = Field(
        default_factory=lambda: ['1m'], min_length=1, max_length=7)
    directions: list[Literal['long', 'short']] = Field(default_factory=lambda: ['long', 'short'], min_length=1, max_length=2)
    minimum_trades: int = Field(default=30, ge=1, le=10000, strict=True)
    max_development_drawdown_percent: float = Field(default=20, gt=0, le=100)
    # Cost identity must come from the normal, instrument-aware engine configuration.
    costs: Literal['require_explicit_engine_configuration'] = 'require_explicit_engine_configuration'
    code_generation: bool = False
    concept_research: bool = True
    external_research: bool = False
    send_development_summaries: bool = False
    holdout: Literal['human_approval', 'one_frozen_candidate'] = 'human_approval'
    max_failed_hypotheses_per_family: int = Field(default=3, ge=1, le=10, strict=True)
    max_parameter_hypotheses_per_family: int = Field(default=2, ge=0, le=10, strict=True)
    dataset: DatasetPolicy = Field(default_factory=DatasetPolicy)
    budget: CampaignBudget = Field(default_factory=CampaignBudget)

    @model_validator(mode='after')
    def normalize(self):
        from app.data.instruments import normalize_symbol
        self.symbols = list(dict.fromkeys(normalize_symbol(s) for s in self.symbols))
        if any(not s or len(s) > 80 for s in self.symbols):
            raise ValueError('Nonempty symbols are required')
        self.timeframes = list(dict.fromkeys(self.timeframes))
        self.directions = list(dict.fromkeys(self.directions))
        if self.dataset.min_development_sessions < self.dataset.internal_windows:
            raise ValueError('Each internal development window needs at least one session')
        if self.code_generation and (not self.send_development_summaries or not self.budget.children):
            raise ValueError('Code generation requires model consent and a positive child budget')
        if self.external_research and not self.budget.external_searches:
            raise ValueError('External research requires a positive search budget')
        return self


def preset(name):
    """Inspectable ceilings, not promises to spend the allowance or find an edge."""
    values = {
        'QUICK': dict(wall_minutes=60, simulations=24, hypotheses=3, children=2,
                      families=2, llm_calls=12, llm_usd=2, compute_minutes=45),
        'STANDARD': {},
        'DEEP': dict(wall_minutes=2880, simulations=600, hypotheses=60, children=30,
                     families=10, llm_calls=180, llm_usd=30, compute_minutes=1440),
    }
    if name not in values:
        raise ValueError('Unknown research intensity; CUSTOM requires an explicit policy')
    return CampaignPolicy(budget=CampaignBudget(**values[name]))
