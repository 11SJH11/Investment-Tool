"""Opt-in OpenAI Responses adapter. No tools, retries, redirects or exception bodies."""
import json
import re
import httpx
from .spending import quote


class ModelFailure(ValueError):
    pass


def strict_schema(model):
    schema = model.model_json_schema()
    def visit(node):
        if isinstance(node, dict):
            node.pop('default', None)
            if node.get('type') == 'object':
                node['additionalProperties'] = False
                node['required'] = list(node.get('properties', {}))
            for value in node.values(): visit(value)
        elif isinstance(node, list):
            for value in node: visit(value)
    visit(schema)
    return schema


class OpenAICommitteeModel:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def status(self):
        model = self.settings.research_llm_model
        valid = bool(re.fullmatch(r'[a-zA-Z0-9_.:-]{1,100}', model))
        return {'configured': bool(self.settings.research_llm_enabled and self.settings.research_llm_api_key and valid),
                'provider': 'openai', 'model': model if valid else None, 'pricing':quote(self.settings), 'execution_enabled': False}

    def generate(self, role, instructions, evidence, model):
        if not self.status()['configured']:
            raise ModelFailure('model_not_configured')
        body = {'model': self.settings.research_llm_model, 'store': False,
                'instructions': instructions, 'input': json.dumps(evidence, allow_nan=False),
                'max_output_tokens': self.settings.research_llm_max_output_tokens,
                'text': {'format': {'type': 'json_schema', 'name': role, 'strict': True, 'schema': strict_schema(model)}}}
        if len(json.dumps(body).encode()) > 90000:
            raise ModelFailure('model_input_limit')
        try:
            with httpx.Client(timeout=60, follow_redirects=False, transport=self.transport, trust_env=False) as client:
                with client.stream('POST', 'https://api.openai.com/v1/responses',
                                   headers={'Authorization': 'Bearer ' + self.settings.research_llm_api_key}, json=body) as response:
                    if response.status_code != 200:
                        category = 'model_rate_limited' if response.status_code == 429 else 'model_authentication' if response.status_code in (401,403) else 'model_provider_error'
                        raise ModelFailure(category)
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 262144: raise ModelFailure('model_output_limit')
                    result = json.loads(data)
            if result.get('status') != 'completed': raise ModelFailure('model_incomplete')
            content = [c for item in result.get('output', []) if item.get('type') == 'message' for c in item.get('content', [])]
            if any(c.get('type') == 'refusal' for c in content): raise ModelFailure('model_refusal')
            texts = [c['text'] for c in content if c.get('type') == 'output_text']
            if len(texts) != 1: raise ModelFailure('model_invalid_output')
            parsed = model.model_validate_json(texts[0]).model_dump()
            usage = result.get('usage') or {}
            counts = {k: usage[k] for k in ('input_tokens','output_tokens','total_tokens') if type(usage.get(k)) is int and usage[k] >= 0}
            if isinstance(result.get('model'),str) and re.fullmatch(r'[a-zA-Z0-9_.:-]{1,100}',result['model']):counts['resolved_model']=result['model']
            return parsed, counts
        except ModelFailure:
            raise
        except Exception:
            raise ModelFailure('model_invalid_output_or_transport_failure') from None
