import json
from .providers import OpenRouter, Gemini, NVIDIA, Ollama
from .model_catalog import HEAD_MODELS, FIX_MODELS, provider_for, model_capabilities, split_model_key

class AIProviderManager:
    """Three-provider team: Gemini Head AI + OpenRouter + NVIDIA NIM specialists."""
    def __init__(self,s):
        self.settings=s
        self.head_model=s.ai_head_model or HEAD_MODELS[0]
        self.fix_models=list(s.ai_fix_models_list)
        self._providers={}; self._configure()

    def _configure(self):
        # Provider identity is explicit; overlapping model IDs can exist on two providers.
        from .model_catalog import MODEL_OPTIONS
        for p,model in MODEL_OPTIONS:
            key=f'{p}::{model}'
            if p=='gemini' and self.settings.gemini_api_key:
                self._providers[key]=Gemini(self.settings.gemini_api_key,model)
            elif p=='openrouter' and self.settings.openrouter_api_key:
                self._providers[key]=OpenRouter(self.settings.openrouter_api_key,model)
            elif p=='nvidia' and self.settings.nvidia_api_key:
                self._providers[key]=NVIDIA(self.settings.nvidia_api_key,model,self.settings.nvidia_base_url)
        # Backward-compatible unqualified IDs point to their first catalog entry.
        for key in list(self._providers):
            p,model=key.split('::',1)
            self._providers.setdefault(model,self._providers[key])
        if self.settings.ollama_api_key:
            self._providers[self.settings.ollama_model]=Ollama(self.settings.ollama_base_url,self.settings.ollama_model)

    def available_models(self): return list(self._providers)
    def provider_name(self,model): return split_model_key(model)[0]
    def capabilities(self,model): return model_capabilities(split_model_key(model)[1])

    async def ask_model(self,model,prompt,*,system=None):
        provider=self._providers.get(model)
        if not provider and '::' not in model:
            provider=self._providers.get(model)
        if not provider: raise RuntimeError(f'Model not configured or API key unavailable: {model}')
        return await provider.ask(prompt,system=system)

    async def ask_multimodal(self,model,prompt,parts,*,system=None):
        provider=self._providers.get(model)
        if not provider and '::' not in model:
            provider=self._providers.get(model)
        if not provider: raise RuntimeError(f'Model not configured: {model}')
        if not (self.capabilities(model) & {p.get('kind') for p in parts}):
            # Text extracted from unsupported binary files can still be sent to text models.
            text_parts=[p for p in parts if p.get('kind')=='text']
            if not text_parts: raise RuntimeError(f'{model} does not support this media type')
            return await provider.ask_multimodal(prompt,text_parts,system=system)
        return await provider.ask_multimodal(prompt,parts,system=system)

    async def choose_fixer(self,problem,*,available=None):
        pool=[m for m in self._providers if '::' in m and m.split('::',1)[1] != self.head_model]
        if not pool: raise RuntimeError('No fixer AI model is configured.')
        prompt=('Select exactly one model for fixing this GitHub build failure.\n'
                'Return JSON only: {"model":"<exact model id>","reason":"short reason"}.\n\n'
                f'Available models: {json.dumps(pool)}\n\nProblem:\n{problem[:16000]}')
        try:
            raw=await self.ask_model(self.head_model,prompt,system='You are Gitofy Head AI. Route failures to the best specialist. Prefer coding-capable models for code/build failures, vision models for image evidence, and NVIDIA NIM when its specialist capability is a better fit.')
            data=json.loads(raw.strip().strip('`').replace('json\n','',1)); chosen=data.get('model')
            if chosen in pool: return chosen,data.get('reason','Selected by Head AI')
            # Head AI may return the bare model identifier; resolve it against the pool.
            matches=[x for x in pool if x.endswith('::'+str(chosen))]
            if matches: return matches[0],data.get('reason','Selected by Head AI')
        except Exception: pass
        # Deterministic quality fallback: code models first, then remaining pool.
        priority=['deepseek-ai/deepseek-v4-pro-0813','qwen/qwen3.8-flash','minimaxai/minimax-m3','minimax/minimax-m3:free','cohere/north-mini-code:free','openai/gpt-4o-mini','nvidia/nemotron-3.5-lightning-30b-a3b']
        for m in priority:
            matches=[x for x in pool if x.endswith('::'+m)]
            if matches: return matches[0],'Deterministic coding-specialist fallback'
        return pool[0],'Head AI routing fallback'

    def is_configured(self,model): return model in self._providers
    def required_api_status(self):
        return {'gemini':bool(self.settings.gemini_api_key),'openrouter':bool(self.settings.openrouter_api_key),'nvidia':bool(self.settings.nvidia_api_key)}

    async def ask(self,prompt,preferred='auto'):
        if preferred and preferred!='auto': return preferred,await self.ask_model(preferred,prompt)
        model=self.head_model if self.head_model in self._providers else next(iter(self._providers),None)
        if not model: raise RuntimeError('No AI model is configured')
        return model,await self.ask_model(model,prompt)
