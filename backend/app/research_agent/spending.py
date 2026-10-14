"""Conservative quote-based local reservations, not an invoice reconciliation."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import math
from .input_limits import MODEL_INPUT_TOKEN_RESERVATION

# Keep the reservation above the bounded serialized request including schemas.
INPUT_TOKEN_RESERVATION = MODEL_INPUT_TOKEN_RESERVATION


def quote(settings):
    incoming=getattr(settings,'research_llm_input_usd_per_million',0)
    outgoing=getattr(settings,'research_llm_output_usd_per_million',0)
    if not all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in (incoming,outgoing)):return None
    output=settings.research_llm_max_output_tokens
    cost=Decimal(str(incoming))*INPUT_TOKEN_RESERVATION+Decimal(str(outgoing))*output
    return {'model':settings.research_llm_model,'input_usd_per_million':incoming,'output_usd_per_million':outgoing,
        'input_token_reservation':INPUT_TOKEN_RESERVATION,'output_token_reservation':output,
        'call_reservation_microusd':int(cost.to_integral_value(rounding=ROUND_CEILING))}


def limit_microusd(value):
    return int((Decimal(str(value))*1000000).to_integral_value(rounding=ROUND_FLOOR))


def usage_cost(usage, pricing):
    if not pricing:return None
    if any(type(usage.get(k)) is not int or usage[k]<0 for k in ('input_tokens','output_tokens')):return None
    cost=Decimal(str(pricing['input_usd_per_million']))*usage['input_tokens']+Decimal(str(pricing['output_usd_per_million']))*usage['output_tokens']
    return int(cost.to_integral_value(rounding=ROUND_CEILING))
