from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ConceptRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    key: str = Field(pattern=r'^(?:strategy-local:)?[a-z][a-z0-9_]*[.][a-z][a-z0-9_]*[.]v[1-9][0-9]*$')
    timeframe: Literal['1m','5m','15m','30m','1h','4h','1d','1w']='1m'
    params: dict = Field(default_factory=dict)

class Observation(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,allow_inf_nan=False,revalidate_instances='always')
    kind: Literal['series','point','event','zone','state']
    label: str
    occurred_at: datetime
    confirmed_at: datetime
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    @model_validator(mode='after')
    def causal_contract(self):
        if self.occurred_at.utcoffset() is None or self.confirmed_at.utcoffset() is None:
            raise ValueError('Concept timestamps must have a timezone')
        if self.confirmed_at<self.occurred_at:raise ValueError('Confirmation cannot precede occurrence')
        if self.kind=='zone' and (self.lower is None or self.upper is None or self.lower>self.upper):
            raise ValueError('A zone needs ordered bounds')
        return self
