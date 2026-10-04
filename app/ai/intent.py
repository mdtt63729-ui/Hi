import json,re
class IntentEngine:
    async def detect(self,manager,text):
        prompt='Return JSON only with keys action, repository, branch, workflow, inputs, confidence. User request: '+text
        try:
            _,raw=await manager.ask(prompt); m=re.search(r'\{.*\}',raw,re.S); return json.loads(m.group(0)) if m else {'action':'unknown','confidence':0}
        except Exception: return {'action':'unknown','confidence':0}
