import base64
import httpx

class Provider:
    async def ask(self, prompt, *, system=None):
        raise RuntimeError("Provider implementation is unavailable")

    async def ask_multimodal(self, prompt, parts, *, system=None):
        raise RuntimeError("This provider does not support multimodal input")

class OpenRouter(Provider):
    def __init__(self, key, model):
        self.key, self.model = key, model

    def _messages(self, prompt, parts=None, system=None):
        messages=[]
        if system: messages.append({"role":"system","content":system})
        if not parts:
            content=prompt
        else:
            content=[{"type":"text","text":prompt}]
            for p in parts:
                if p["kind"] == "image":
                    b64=base64.b64encode(p["data"]).decode()
                    content.append({"type":"image_url","image_url":{"url":f"data:{p['mime']};base64,{b64}"}})
                elif p["kind"] == "text":
                    content.append({"type":"text","text":p["text"]})
                else:
                    content.append({"type":"text","text":f"[Attachment: {p.get('name','file')} — {p.get('mime','unknown')}]\n{p.get('text','')}"})
        messages.append({"role":"user","content":content})
        return messages

    async def _post(self, messages):
        if not self.key: raise RuntimeError("OpenRouter not configured")
        async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=20)) as c:
            r=await c.post("https://openrouter.ai/api/v1/chat/completions",headers={
                "Authorization":f"Bearer {self.key}","Content-Type":"application/json",
                "HTTP-Referer":"https://gitofy.local","X-Title":"Gitofy"},
                json={"model":self.model,"messages":messages,"temperature":0.1})
            r.raise_for_status(); data=r.json()
            return data["choices"][0]["message"]["content"]

    async def ask(self,prompt,*,system=None): return await self._post(self._messages(prompt,system=system))
    async def ask_multimodal(self,prompt,parts,*,system=None): return await self._post(self._messages(prompt,parts,system))

class Gemini(Provider):
    def __init__(self,key,model): self.key,self.model=key,model

    async def ask(self,prompt,*,system=None):
        if not self.key: raise RuntimeError("Gemini not configured")
        parts=[]
        if system: parts.append({"text":system})
        parts.append({"text":prompt})
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(240,connect=20)) as c:
            r=await c.post(url,json={"contents":[{"role":"user","parts":parts}],"generationConfig":{"temperature":0.1}})
            r.raise_for_status(); return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    async def ask_multimodal(self,prompt,parts,*,system=None):
        if not self.key: raise RuntimeError("Gemini not configured")
        gparts=[]
        if system: gparts.append({"text":system})
        gparts.append({"text":prompt})
        for p in parts:
            if p["kind"] in {"image","binary"}:
                gparts.append({"inline_data":{"mime_type":p["mime"],"data":base64.b64encode(p["data"]).decode()}})
            elif p["kind"]=="text":
                gparts.append({"text":p["text"]})
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(300,connect=20)) as c:
            r=await c.post(url,json={"contents":[{"role":"user","parts":gparts}],"generationConfig":{"temperature":0.1}})
            r.raise_for_status(); return r.json()["candidates"][0]["content"]["parts"][0]["text"]

class NVIDIA(Provider):
    """NVIDIA NIM OpenAI-compatible chat client.

    Multimodal images use the same content array format documented by NVIDIA.
    """
    def __init__(self,key,model,base_url="https://integrate.api.nvidia.com/v1"):
        self.key,self.model,self.base_url=key,model,base_url.rstrip("/")

    def _messages(self,prompt,parts=None,system=None):
        messages=[]
        if system: messages.append({"role":"system","content":system})
        if not parts: content=prompt
        else:
            content=[{"type":"text","text":prompt}]
            for p in parts:
                if p["kind"]=="image":
                    b64=base64.b64encode(p["data"]).decode()
                    content.append({"type":"image_url","image_url":{"url":f"data:{p['mime']};base64,{b64}"}})
                elif p["kind"]=="text": content.append({"type":"text","text":p["text"]})
                else: content.append({"type":"text","text":f"[Attachment {p.get('name','file')}]\n{p.get('text','')}"})
        messages.append({"role":"user","content":content}); return messages

    async def _post(self,messages):
        if not self.key: raise RuntimeError("NVIDIA API not configured")
        async with httpx.AsyncClient(timeout=httpx.Timeout(300,connect=20)) as c:
            r=await c.post(self.base_url+"/chat/completions",headers={
                "Authorization":f"Bearer {self.key}","Accept":"application/json","Content-Type":"application/json"},
                json={"messages":messages,"model":self.model,"max_tokens":16384,"seed":0,"stream":False,"temperature":0.1,"reasoning_effort":"max"})
            r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]

    async def ask(self,prompt,*,system=None): return await self._post(self._messages(prompt,system=system))
    async def ask_multimodal(self,prompt,parts,*,system=None): return await self._post(self._messages(prompt,parts,system))

class Ollama(Provider):
    def __init__(self,url,model): self.url,self.model=url.rstrip('/'),model
    async def ask(self,prompt,*,system=None):
        messages=[]
        if system: messages.append({'role':'system','content':system})
        messages.append({'role':'user','content':prompt})
        async with httpx.AsyncClient(timeout=120) as c:
            r=await c.post(self.url+'/api/chat',json={'model':self.model,'messages':messages,'stream':False})
            r.raise_for_status(); return r.json()['message']['content']
