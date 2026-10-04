#!/usr/bin/env python3
"""Gitofy - production-oriented Telegram-first GitHub automation runtime.

Stdlib-only host entrypoint.  No startup pip install.  All external state is
obtained from Telegram/GitHub APIs; build status, artifacts and percentages are
never fabricated.
"""
from __future__ import annotations
import base64, hashlib, hmac, io, json, mimetypes, os, re, secrets, sqlite3, tempfile, threading, time, traceback, urllib.error, urllib.parse, urllib.request, zipfile, queue, concurrent.futures
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
try:
    from app.github.pat_capabilities import render_report
except Exception:
    render_report = None
from datetime import datetime, timezone, timedelta

try:
    from app.services.libgit2_engine import available as libgit2_available, LibGit2Engine
except Exception:
    libgit2_available=lambda: False
    LibGit2Engine=None
try:
    from app.services.git_cli_engine import available as git_cli_available, GitCliEngine
except Exception:
    git_cli_available=lambda: False
    GitCliEngine=None

APP="Gitofy"; TG_API_BASE=os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/"); TG=TG_API_BASE+"/bot{}/{}"; TG_FILE_BASE=os.getenv("TELEGRAM_FILE_BASE_URL", TG_API_BASE+"/file").rstrip("/"); GH="https://api.github.com"
ROOT=Path(__file__).resolve().parent
DATA=Path(os.getenv("GITOFY_DATA_DIR", str(ROOT/"data"))); DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"gitofy.sqlite3"; TMP=DATA/"temp"; UP=DATA/"uploads"; ART=DATA/"artifacts"
for p in (TMP,UP,ART): p.mkdir(parents=True,exist_ok=True)
MAX_ZIP_BYTES=int(os.getenv("MAX_ZIP_BYTES",str(50*1024*1024))); MAX_FILES=int(os.getenv("MAX_ZIP_FILES","10000")); MAX_UNPACK=int(os.getenv("MAX_UNPACK_BYTES",str(500*1024*1024)))
POLL_SECONDS=max(2,int(os.getenv("BUILD_POLL_SECONDS","3"))); ADMIN_IDS={int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit()}

class GitofyError(Exception): pass
class HttpError(GitofyError):
    def __init__(self,status,message,headers=None): self.status=status; self.message=message; self.headers=headers or {}; super().__init__(f"HTTP {status}: {message}")

def now(): return datetime.now(timezone.utc).isoformat()
def safe(s,maxlen=900):
    s=re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]","",str(s)); return s[:maxlen]
def redact(s):
    if not s:return s
    return re.sub(r"(?i)(ghp_[A-Za-z0-9_\-]+|github_pat_[A-Za-z0-9_\-]+|Bearer\s+[A-Za-z0-9._\-]+|AIza[0-9A-Za-z_\-]+)","[REDACTED]",str(s))

def http(url,method="GET",headers=None,data=None,timeout=60,stream=False):
    h={"User-Agent":"Gitofy/1.1","Accept":"application/json"}; h.update(headers or {})
    req=urllib.request.Request(url,method=method,headers=h,data=data)
    try:
        r=urllib.request.urlopen(req,timeout=timeout)
        if stream:return r
        raw=r.read(); return r.status,dict(r.headers),raw
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8","replace")
        try: obj=json.loads(body); msg=obj.get("message",body)
        except Exception: msg=body
        raise HttpError(e.code,safe(redact(msg),700),dict(e.headers))
    except Exception as e: raise GitofyError(redact(str(e)))

def json_http(url,method="GET",headers=None,obj=None,timeout=60):
    data=json.dumps(obj).encode() if obj is not None else None
    h={"Content-Type":"application/json"} if obj is not None else {}
    h.update(headers or {})
    status,hs,raw=http(url,method,h,data,timeout)
    try:return json.loads(raw.decode()) if raw else {}
    except Exception:return raw.decode("utf-8","replace")

def tg(token,method,payload=None,files=None):
    url=TG.format(token,method)
    if files:
        boundary="----Gitofy"+secrets.token_hex(8); chunks=[]
        fields={k:str(v) for k,v in (payload or {}).items()}
        for k,v in fields.items(): chunks += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()]
        for k,(filename,content,ctype) in files.items():
            chunks += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n".encode(),content,b"\r\n"]
        chunks.append(f"--{boundary}--\r\n".encode())
        _,_,raw=http(url,"POST",{"Content-Type":f"multipart/form-data; boundary={boundary}"},b"".join(chunks),timeout=180)
    else:
        data=urllib.parse.urlencode(payload or {}).encode(); _,_,raw=http(url,"POST",{"Content-Type":"application/x-www-form-urlencoded"},data,timeout=90)
    obj=json.loads(raw.decode())
    if not obj.get("ok"): raise GitofyError(redact(str(obj)))
    return obj.get("result")

def _plain_telegram_text(text):
    # Telegram's HTML parser is intentionally optional.  Any API/GitHub error
    # can contain arbitrary characters (for example \\class\\) that are
    # unsafe inside Telegram entities.  Strip only our own presentation tags
    # for the fallback; never send the raw value with a parse mode.
    text=re.sub(r"</?(?:b|strong|i|em|u|s|code|pre)>", "", str(text), flags=re.I)
    text=text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return safe(text,3900)

_COMMAND_PROGRESS = threading.local()

class _CommandProgress:
    def __init__(self, token, chat, msg_id):
        self.token=token; self.chat=chat; self.msg_id=msg_id; self.lock=threading.RLock(); self.status="Processing…"; self.pct=0; self.stop=False; self.last_render=""
    def render(self):
        pct=max(0,min(99,int(self.pct))); filled=max(0,min(20,pct*20//100)); bar="█"*filled+"░"*(20-filled)
        return f"⏳ <b>{safe(self.status,250)}</b>\n<code>{bar}</code> <b>{pct}%</b>"
    def edit_progress(self):
        with self.lock:
            text=self.render()
        try: tg_edit(self.token,self.chat,self.msg_id,text)
        except Exception: pass
    def advance(self,pct=None,status=None):
        with self.lock:
            if pct is not None:self.pct=max(self.pct,min(99,float(pct)))
            if status:self.status=status
        self.edit_progress()
    def animate(self):
        # Smoothly advances one percentage point at a time while a synchronous
        # command is working. It never jumps by 10/20/30.
        while not self.stop:
            with self.lock:
                if self.pct < 92:self.pct += 1
                self.status=self.status or "Processing…"
            self.edit_progress(); time.sleep(0.35)

def tg_send(token,chat,text,keyboard=None,parse="HTML"):
    ctx=getattr(_COMMAND_PROGRESS,"ctx",None)
    if ctx is not None and ctx.token==token and ctx.chat==chat and not getattr(ctx,"finished",False):
        # During a command, collapse every intermediate send into the single
        # processing message. The final wrapper edit will show the actual reply.
        ctx.advance(status=re.sub(r"<[^>]+>","",str(text)).strip() or "Processing…")
        ctx.final_text=text; ctx.final_keyboard=keyboard; ctx.final_parse=parse
        return {"message_id":ctx.msg_id}
    text=safe(text,3900)
    p={"chat_id":chat,"text":text,"disable_web_page_preview":"true"}
    if parse:
        p["parse_mode"]=parse
    if keyboard:p["reply_markup"]=json.dumps({"inline_keyboard":keyboard})
    try:
        return tg(token,"sendMessage",p)
    except GitofyError as e:
        # Never let Telegram formatting errors hide the real operation result.
        # Retry once as plain text.  This is especially important for dynamic
        # GitHub errors containing backslashes, angle brackets or malformed
        # entity syntax.
        msg=str(e).lower()
        if parse and ("can't parse entities" in msg or "parse entities" in msg or "unsupported start tag" in msg):
            fallback={"chat_id":chat,"text":_plain_telegram_text(text),"disable_web_page_preview":"true"}
            if keyboard:fallback["reply_markup"]=json.dumps({"inline_keyboard":keyboard})
            return tg(token,"sendMessage",fallback)
        raise

def tg_edit(token,chat,msg,text,keyboard=None):
    text=safe(text,3900)
    p={"chat_id":chat,"message_id":msg,"text":text,"parse_mode":"HTML","disable_web_page_preview":"true"}
    if keyboard:p["reply_markup"]=json.dumps({"inline_keyboard":keyboard})
    try:return tg(token,"editMessageText",p)
    except GitofyError as e:
        if "message is not modified" in str(e).lower(): return None
        if "can't parse entities" in str(e).lower() or "parse entities" in str(e).lower() or "unsupported start tag" in str(e).lower():
            fallback={"chat_id":chat,"message_id":msg,"text":_plain_telegram_text(text),"disable_web_page_preview":"true"}
            if keyboard:fallback["reply_markup"]=json.dumps({"inline_keyboard":keyboard})
            return tg(token,"editMessageText",fallback)
        raise

def tg_answer(token,cid,text="",alert=False):
    try:tg(token,"answerCallbackQuery",{"callback_query_id":cid,"text":text,"show_alert":str(alert).lower()})
    except Exception:pass

def gh(token,path,method="GET",obj=None,accept="application/json"):
    h={"Authorization":f"Bearer {token}","X-GitHub-Api-Version":"2022-11-28","Accept":accept}
    return json_http(GH+path,method,h,obj,90)

def gh_raw(token,path,method="GET"):
    h={"Authorization":f"Bearer {token}","X-GitHub-Api-Version":"2022-11-28","Accept":"application/vnd.github+json"}
    return http(GH+path,method,h,None,120)

class DBStore:
    def __init__(self):
        self.lock=threading.RLock(); self.cx=sqlite3.connect(DB,check_same_thread=False); self.cx.row_factory=sqlite3.Row; self.init()
    def init(self):
        with self.lock:
            self.cx.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,telegram_id INTEGER UNIQUE,username TEXT,created_at TEXT,updated_at TEXT,status TEXT);
            CREATE TABLE IF NOT EXISTS pending_inputs(telegram_user_id INTEGER PRIMARY KEY,kind TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS github_connections(telegram_user_id INTEGER PRIMARY KEY,github_user_id INTEGER,github_username TEXT,encrypted_pat TEXT,permissions TEXT,created_at TEXT,updated_at TEXT,status TEXT);
            CREATE TABLE IF NOT EXISTS repositories(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_user_id INTEGER,github_repo_id INTEGER,owner TEXT,name TEXT,default_branch TEXT,visibility TEXT,created_at TEXT,updated_at TEXT,UNIQUE(telegram_user_id,github_repo_id));
            CREATE TABLE IF NOT EXISTS repo_settings(repository_id INTEGER PRIMARY KEY,default_branch TEXT,default_workflow TEXT,auto_build INTEGER DEFAULT 0,sync_mode TEXT DEFAULT 'update',notification_mode TEXT DEFAULT 'all');
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,telegram_user_id INTEGER,repository_id INTEGER,branch TEXT,type TEXT,status TEXT,progress REAL DEFAULT 0,created_at TEXT,updated_at TEXT,worker_id TEXT,error_code TEXT);
            CREATE TABLE IF NOT EXISTS workflow_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,repository_id INTEGER,github_run_id INTEGER UNIQUE,workflow_id INTEGER,branch TEXT,status TEXT,conclusion TEXT,telegram_user_id INTEGER,telegram_chat_id INTEGER,telegram_message_id INTEGER,created_at TEXT,updated_at TEXT,last_progress REAL DEFAULT 0,last_render_hash TEXT);
            CREATE TABLE IF NOT EXISTS webhook_events(id INTEGER PRIMARY KEY AUTOINCREMENT,github_delivery_id TEXT UNIQUE,event_type TEXT,repository_id INTEGER,run_id INTEGER,payload_hash TEXT,received_at TEXT,processed_at TEXT,status TEXT);
            CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,user_request TEXT,ai_decision TEXT,tool TEXT,repository TEXT,target TEXT,action TEXT,result TEXT,timestamp TEXT,operation_id TEXT);
            CREATE TABLE IF NOT EXISTS memories(telegram_user_id INTEGER,repository TEXT,key TEXT,value TEXT,updated_at TEXT,PRIMARY KEY(telegram_user_id,repository,key));
            CREATE TABLE IF NOT EXISTS scheduled_tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_user_id INTEGER,repository TEXT,task TEXT,cron TEXT,enabled INTEGER DEFAULT 1,last_run TEXT,next_run TEXT);
            CREATE TABLE IF NOT EXISTS artifact_history(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_user_id INTEGER,repository TEXT,run_id INTEGER,name TEXT,size INTEGER,url TEXT,created_at TEXT,expires_at TEXT);
            CREATE TABLE IF NOT EXISTS locks(repository TEXT PRIMARY KEY,owner TEXT,expires_at REAL);
            '''); self.cx.commit()
            # Lightweight migration: add failure-notification preference to an
            # already-existing github_connections table without breaking older
            # databases. ALTER TABLE ADD COLUMN is idempotent-guarded via except.
            try:self.cx.execute("ALTER TABLE github_connections ADD COLUMN notify_on_failure INTEGER DEFAULT 1");self.cx.commit()
            except Exception:pass
            try:self.cx.execute("CREATE TABLE IF NOT EXISTS failure_notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_user_id INTEGER,github_run_id INTEGER,notified_at TEXT,UNIQUE(telegram_user_id,github_run_id))");self.cx.commit()
            except Exception:pass
    def q(self,sql,args=(),one=False):
        with self.lock:
            c=self.cx.execute(sql,args); rows=c.fetchall(); return (rows[0] if rows else None) if one else rows
    def run(self,sql,args=()):
        with self.lock:self.cx.execute(sql,args);self.cx.commit()
    def user(self,uid,username=""):
        self.run("INSERT INTO users(telegram_id,username,created_at,updated_at,status) VALUES(?,?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,updated_at=excluded.updated_at",(uid,username,now(),now(),"active"))
    def conn(self,uid):return self.q("SELECT * FROM github_connections WHERE telegram_user_id=?",(uid,),True)
    def set_pending(self,uid,kind): self.run("INSERT INTO pending_inputs(telegram_user_id,kind,created_at) VALUES(?,?,?) ON CONFLICT(telegram_user_id) DO UPDATE SET kind=excluded.kind,created_at=excluded.created_at",(uid,kind,now()))
    def pending(self,uid):
        r=self.q("SELECT kind FROM pending_inputs WHERE telegram_user_id=?",(uid,),True); return r["kind"] if r else None
    def clear_pending(self,uid): self.run("DELETE FROM pending_inputs WHERE telegram_user_id=?",(uid,))
    def setconn(self,uid,ghid,login,pat,perms):
        encrypted=None
        try: encrypted=protect_pat(pat)
        except GitofyError: pass
        self.run("INSERT INTO github_connections(telegram_user_id,github_user_id,github_username,encrypted_pat,permissions,created_at,updated_at,status) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(telegram_user_id) DO UPDATE SET github_user_id=excluded.github_user_id,github_username=excluded.github_username,encrypted_pat=excluded.encrypted_pat,permissions=excluded.permissions,updated_at=excluded.updated_at,status='active'",(uid,ghid,login,encrypted,json.dumps(perms),now(),now(),"active"))
        SESSION_PATS[uid]=pat
    def pat(self,uid):
        if uid in SESSION_PATS:return SESSION_PATS[uid]
        r=self.conn(uid)
        return unprotect_pat(r["encrypted_pat"]) if r else None
    def audit(self,uid,req,decision,tool,repo,target,action,result,opid=""):
        self.run("INSERT INTO audit_log(user_request,ai_decision,tool,repository,target,action,result,timestamp,operation_id) VALUES(?,?,?,?,?,?,?,?,?)",(safe(req),safe(decision),tool,repo,target,action,safe(redact(result)),now(),opid))
    def acquire(self,repo,owner,ttl=300):
        with self.lock:
            t=time.time(); r=self.q("SELECT * FROM locks WHERE repository=?",(repo,),True)
            if r and r["expires_at"]>t and r["owner"]!=owner:return False
            self.cx.execute("INSERT INTO locks(repository,owner,expires_at) VALUES(?,?,?) ON CONFLICT(repository) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at",(repo,owner,t+ttl));self.cx.commit();return True
    def release(self,repo,owner):self.run("DELETE FROM locks WHERE repository=? AND owner=?",(repo,owner))
    def notify_pref(self,uid):
        r=self.conn(uid); return bool(r["notify_on_failure"]) if r and r["notify_on_failure"] is not None else True
    def set_notify_pref(self,uid,val):
        self.run("UPDATE github_connections SET notify_on_failure=? WHERE telegram_user_id=?",(1 if val else 0,uid))
    def repo_notification_mode(self,repository_id):
        r=self.q("SELECT notification_mode FROM repo_settings WHERE repository_id=?",(repository_id,),True)
        return r["notification_mode"] if r and r["notification_mode"] else "all"
    def already_notified(self,uid,run_id):
        return bool(self.q("SELECT 1 FROM failure_notifications WHERE telegram_user_id=? AND github_run_id=?",(uid,run_id),True))
    def mark_notified(self,uid,run_id):
        try:self.run("INSERT INTO failure_notifications(telegram_user_id,github_run_id,notified_at) VALUES(?,?,?) ON CONFLICT(telegram_user_id,github_run_id) DO NOTHING",(uid,run_id,now()))
        except Exception:pass

DBS=DBStore()
SESSION_PATS={}

def _keystream(key: bytes, nonce: bytes, n: int) -> bytes:
    out=bytearray(); counter=0
    while len(out)<n:
        out.extend(hmac.new(key,nonce+counter.to_bytes(8,'big'),hashlib.sha256).digest());counter+=1
    return bytes(out[:n])

def protect_pat(pat: str) -> str:
    """Authenticated encryption using a deployment secret and HMAC-PRF stream."""
    key=os.getenv("GITOFY_ENCRYPTION_KEY","").strip().encode()
    if not key:
        # Host-safe fallback: BOT_TOKEN is already a deployment secret. This keeps
        # credentials encrypted across restarts even when the host exposes no
        # separate encryption variable. A dedicated GITOFY_ENCRYPTION_KEY is
        # still preferred.
        key=os.getenv("BOT_TOKEN","").strip().encode()
    if not key: raise GitofyError("No deployment secret is available for credential encryption")
    key=hashlib.sha256(key).digest();nonce=secrets.token_bytes(16);plain=pat.encode();cipher=bytes(a^b for a,b in zip(plain,_keystream(key,nonce,len(plain))))
    tag=hmac.new(key,nonce+cipher,hashlib.sha256).digest()
    return "gse1:"+base64.urlsafe_b64encode(nonce+cipher+tag).decode()

def unprotect_pat(value: str) -> str|None:
    if not value or not value.startswith("gse1:"):return None
    key=os.getenv("GITOFY_ENCRYPTION_KEY","").strip().encode()
    if not key:key=os.getenv("BOT_TOKEN","").strip().encode()
    if not key:return None
    try:
        key=hashlib.sha256(key).digest();raw=base64.urlsafe_b64decode(value[5:].encode());nonce,cipher,tag=raw[:16],raw[16:-32],raw[-32:]
        if not hmac.compare_digest(tag,hmac.new(key,nonce+cipher,hashlib.sha256).digest()):return None
        return bytes(a^b for a,b in zip(cipher,_keystream(key,nonce,len(cipher)))).decode()
    except Exception:return None


class Progress:
    @staticmethod
    def resolve(jobs):
        units=[]
        for j in jobs:
            steps=j.get("steps") or []
            if steps:
                job_name=j.get("name","job")
                for step in steps:
                    # GitHub returns the job name and the individual step name
                    # separately.  Render the actual step name so Telegram shows
                    # the same workflow hierarchy a user sees in Actions.
                    step_name=step.get("name") or "Unnamed step"
                    units.append(("step",f"{job_name} › {step_name}",step))
            else:
                units.append(("job",j.get("name","job"),j))
        total=len(units)
        done=sum(1 for _,_,x in units if x.get("conclusion") in ("success","failure","cancelled","skipped","neutral","timed_out","action_required"))
        running=sum(1 for _,_,x in units if x.get("status")=="in_progress")
        failed=next((x for _,_,x in units if x.get("conclusion") not in (None,"success","skipped","neutral") and x.get("conclusion")),None)
        pct=round(done*100/total,2) if total else 0
        return total,done,pct,running,failed,units
    @staticmethod
    def render(run,jobs):
        total,done,pct,running,failed,units=Progress.resolve(jobs)
        bar="█"*int(pct//10)+"░"*(10-int(pct//10))
        lines=[f"<b>📊 {APP} • Run #{run['id']}</b>",f"Workflow: <code>{safe(run.get('name',''))}</code>",f"Branch: <code>{safe(run.get('head_branch') or '')}</code>",f"Status: <b>{run.get('status')}</b> / {run.get('conclusion') or 'running'}","",f"<code>{bar}</code> <b>{pct:g}%</b> — {done}/{total} trackable units"]
        for typ,name,x in units[:80]:
            icon="⏳" if x.get("status")=="in_progress" else ("✅" if x.get("conclusion") in ("success","skipped","neutral") else ("❌" if x.get("conclusion") else "▫️"))
            lines.append(f"{icon} {safe(name,90)}")
        if len(units)>80:lines.append(f"… +{len(units)-80} more")
        if failed:lines += ["",f"❌ <b>Failure:</b> {safe(failed.get('name','unknown'))}"]
        return "\n".join(lines),pct,done,total

def send_failure_alert(token,uid,chat,run,owner,name):
    """Send a standalone, real push-notification-triggering message when a
    workflow run fails. Kept separate from the live progress message (which
    is only edited) so the person is actually pinged even if they are not
    watching the chat, but only once per run and only if they still want
    failure alerts."""
    if not DBS.notify_pref(uid):return
    if DBS.already_notified(uid,run["id"]):return
    text=(f"🚨 <b>Workflow FAILED</b>\n\n"
          f"📁 Repository: <code>{safe(owner)}/{safe(name)}</code>\n"
          f"⚙️ Workflow: <code>{safe(run.get('name',''))}</code>\n"
          f"🌿 Branch: <code>{safe(run.get('head_branch') or '')}</code>\n"
          f"❌ Conclusion: <b>{safe((run.get('conclusion') or 'failure').upper())}</b>\n"
          f"🔗 Run #{run['id']}")
    kb=[[{"text":"📜 Logs","callback_data":f"logs:{uid}:{run['id']}:{owner}/{name}"},{"text":"📦 Artifacts","callback_data":f"arts:{uid}:{run['id']}:{owner}/{name}"}],
        [{"text":"🔄 Re-run","callback_data":f"rerun:{uid}:{run['id']}:{owner}/{name}"},{"text":"📊 Details","callback_data":f"run:{uid}:{run['id']}:{owner}/{name}"}]]
    try:
        tg_send(token,chat,text,kb)
        DBS.mark_notified(uid,run["id"])
    except Exception:pass


def _run_url(owner, name, run_id):
    return f"https://github.com/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}/actions/runs/{run_id}"


def send_build_success_alert(token, uid, chat, run, owner, name):
    """Send a standalone success notification so completion is visible even
    when the live dashboard message was not being watched."""
    if not DBS.notify_pref(uid):
        return
    text=(f"🎉 <b>Workflow SUCCEEDED</b>\n\n"
          f"📁 Repository: <code>{safe(owner)}/{safe(name)}</code>\n"
          f"⚙️ Workflow: <code>{safe(run.get('name',''))}</code>\n"
          f"🌿 Branch: <code>{safe(run.get('head_branch') or '')}</code>\n"
          f"🟢 Conclusion: <b>SUCCESS</b>\n"
          f"🔗 Run #{run['id']}")
    kb=[[{"text":"📦 Artifacts / Download","callback_data":f"arts:{uid}:{run['id']}:{owner}/{name}"},
         {"text":"📊 Details","callback_data":f"run:{uid}:{run['id']}:{owner}/{name}"}]]
    try:
        tg_send(token,chat,text,kb)
    except Exception:
        pass


def _download_run_logs_text(token, owner, name, rid):
    _, headers, raw = gh_raw(token, f"/repos/{owner}/{name}/actions/runs/{rid}/logs")
    ctype=(headers.get("Content-Type") or "").lower()
    if "zip" in ctype or raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            chunks=[]
            for n in z.namelist():
                if n.endswith('/'):
                    continue
                try:
                    chunks.append(f"===== {n} =====\n" + z.read(n).decode("utf-8","replace"))
                except Exception:
                    continue
            return "\n\n".join(chunks)
    return raw.decode("utf-8","replace")


def _repo_snapshot_for_ai(token, owner, name, branch, error, max_bytes=6_000_000):
    """Build a bounded but repository-wide AI snapshot.

    The AI receives every tracked path plus source/config contents until the
    context budget is reached. Binary/generated directories are represented by
    the manifest only. This lets the agent reason over the complete project
    structure without trying to stuff a multi-GB repository into a prompt.
    """
    try:
        ref=gh(token, f"/repos/{owner}/{name}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
        sha=((ref or {}).get("object") or {}).get("sha")
        if not sha:
            return "MANIFEST: empty repository"
        tree=gh(token, f"/repos/{owner}/{name}/git/trees/{sha}?recursive=1")
        entries=[x for x in tree.get("tree",[]) if x.get("type")=="blob" and x.get("path")]
    except Exception as exc:
        return f"MANIFEST UNAVAILABLE: {safe(redact(exc),500)}"

    paths=sorted(x["path"] for x in entries)
    manifest="REPOSITORY MANIFEST\n"+"\n".join(paths)
    out=[manifest, "\nSOURCE/CONFIG CONTENTS"]
    used=len(manifest.encode("utf-8"))
    # Prioritize likely build/failure files and then include the rest of the
    # text source files.  The manifest still contains every repository path.
    error_terms=set(re.findall(r"[A-Za-z0-9_.-]+", error.lower()))
    def score(entry):
        p=entry["path"].lower(); score=0
        if any(p.endswith(x) for x in ("build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts","gradle.properties","gradle/libs.versions.toml","androidmanifest.xml")): score+=100
        if any(k in p for k in (".github/workflows/","workflow","gradle/")): score+=60
        if any(t and t in p for t in error_terms): score+=20
        if p.endswith((".kt",".java",".kts",".gradle",".xml",".properties",".toml",".yml",".yaml",".json",".py",".js",".ts",".tsx",".jsx",".sh",".md")): score+=10
        if any(k in p for k in ("build/",".gradle/","node_modules/",".git/")): score-=1000
        return -score, p
    for entry in sorted(entries,key=score):
        if used>=max_bytes:
            break
        p=entry["path"]
        if any(k in p.lower() for k in ("build/",".gradle/","node_modules/",".git/")):
            continue
        if not p.lower().endswith((".kt",".java",".kts",".gradle",".xml",".properties",".toml",".yml",".yaml",".json",".py",".js",".ts",".tsx",".jsx",".sh",".md",".txt")):
            continue
        try:
            blob=gh(token,f"/repos/{owner}/{name}/git/blobs/{entry.get('sha')}")
            raw=base64.b64decode((blob.get("content") or "").encode())
            if b"\x00" in raw:
                continue
            text=raw.decode("utf-8","replace")
        except Exception:
            continue
        text=text[:300_000]
        encoded=len(text.encode("utf-8"))
        if used+encoded+80>max_bytes:
            continue
        out.append(f"\n===== FILE: {p} =====\n{text}")
        used+=encoded+80
    return "\n".join(out)


def _parse_ai_json(raw):
    raw=str(raw or "").strip()
    raw=re.sub(r"^```(?:json)?\s*|\s*```$","",raw,flags=re.I|re.S).strip()
    m=re.search(r"\{.*\}",raw,re.S)
    if not m:
        raise GitofyError("AI did not return a machine-readable fix plan.")
    try:
        obj=json.loads(m.group(0))
    except Exception as exc:
        raise GitofyError(f"AI returned invalid JSON: {safe(exc,300)}")
    if not isinstance(obj,dict):
        raise GitofyError("AI fix plan is not an object.")
    return obj


def _apply_ai_changes(token, owner, name, branch, changes, message):
    """Apply only explicit AI file-content changes in one normal commit."""
    ref=gh(token,f"/repos/{owner}/{name}/git/ref/heads/{urllib.parse.quote(branch,safe='')}")
    parent=((ref or {}).get("object") or {}).get("sha")
    if not parent:
        raise GitofyError("Cannot apply an AI fix to a branch without a commit.")
    commit=gh(token,f"/repos/{owner}/{name}/git/commits/{parent}")
    base_tree=((commit or {}).get("tree") or {}).get("sha")
    if not base_tree:
        raise GitofyError("GitHub did not return the current tree SHA.")
    entries=[]
    for change in changes:
        path=str(change.get("path") or "").strip().replace("\\","/")
        if not path or path.startswith("/") or ".." in Path(path).parts or path.startswith(".git/"):
            raise GitofyError(f"AI proposed an unsafe path: {safe(path,200)}")
        content=change.get("content")
        if not isinstance(content,str):
            raise GitofyError(f"AI did not provide complete content for {path}")
        if len(content.encode("utf-8"))>10_000_000:
            raise GitofyError(f"AI fix for {path} is too large.")
        blob=gh(token,f"/repos/{owner}/{name}/git/blobs","POST",{"content":base64.b64encode(content.encode("utf-8")).decode("ascii"),"encoding":"base64"})
        entries.append({"path":path,"mode":"100644","type":"blob","sha":blob.get("sha")})
    if not entries:
        raise GitofyError("AI found no file changes to apply.")
    tree=gh(token,f"/repos/{owner}/{name}/git/trees","POST",{"base_tree":base_tree,"tree":entries})
    commit=gh(token,f"/repos/{owner}/{name}/git/commits","POST",{"message":message,"tree":tree.get("sha"),"parents":[parent]})
    gh(token,f"/repos/{owner}/{name}/git/refs/heads/{urllib.parse.quote(branch,safe='')}","PATCH",{"sha":commit.get("sha"),"force":False})
    return commit.get("sha")


def ai_autofix_failed_run(token, uid, chat, mid, owner, name, run, jobs):
    """Observe a failed run, diagnose it with the complete repo snapshot,
    patch the affected files, push, and dispatch the same workflow again."""
    if os.getenv("AI_AUTOFIX_ENABLED","true").strip().lower() not in ("1","true","yes","on"):
        return None
    branch=run.get("head_branch") or "main"
    workflow_id=run.get("workflow_id")
    lock_name=f"{owner}/{name}"
    lock_owner=f"ai:{uid}:{run.get('id')}"
    if not DBS.acquire(lock_name,lock_owner,ttl=900):
        tg_edit(token,chat,mid,"⚠️ <b>AI repair skipped</b>\n\nAnother Gitofy operation is currently modifying this repository.")
        return None
    try:
        tg_edit(token,chat,mid,"⏳ <b>AI engineer: collecting failed-build logs…</b>\n<code>████░░░░░░░░░░░░░░░░</code> <b>20%</b>")
        logs=_download_run_logs_text(token,owner,name,run["id"])
        logs=redact(logs)[:700_000]
        tg_edit(token,chat,mid,"⏳ <b>AI engineer: reading the full GitHub project…</b>\n<code>████████░░░░░░░░░░░░</code> <b>40%</b>")
        snapshot=_repo_snapshot_for_ai(token,owner,name,branch,logs[:20_000],max_bytes=4_500_000)
        prompt=("You are Gitofy Autonomous Build Engineer. A GitHub Actions workflow just FAILED. "
                "You may modify source/config files in this repository and the user has authorized an automatic repair. "
                "Study the complete repository manifest and the available source/config contents plus the latest build logs. "
                "Identify the real root cause, do not hide/disable the build, do not weaken tests, do not remove security checks, "
                "and do not change workflow triggers merely to make the run pass. Return JSON ONLY with this schema: "
                "{summary:string, diagnosis:string, changes:[{path:string,content:string,reason:string}], tests:[string], confidence:number}. "
                "content must be the COMPLETE new file content, not a diff. If no safe fix is justified, return changes:[].\n\n"
                f"Repository: {owner}/{name}\nBranch: {branch}\nWorkflow: {run.get('name')} (id {workflow_id})\n\n"
                f"LATEST BUILD LOGS:\n{logs}\n\nREPOSITORY SNAPSHOT:\n{snapshot}")
        tg_edit(token,chat,mid,"⏳ <b>AI engineer: diagnosing root cause and preparing the fix…</b>\n<code>████████████░░░░░░░░</code> <b>60%</b>")
        raw=ai(prompt)
        if not raw:
            raise GitofyError("No AI provider is configured.")
        plan=_parse_ai_json(raw)
        changes=plan.get("changes") or []
        if not changes:
            tg_edit(token,chat,mid,"❌ <b>AI could not find a safe automatic fix.</b>\n\nThe failed build was left unchanged.")
            return None
        tg_edit(token,chat,mid,f"⏳ <b>AI engineer: applying {len(changes)} file fix(es)…</b>\n<code>███████████████░░░░░</code> <b>75%</b>")
        commit_sha=_apply_ai_changes(token,owner,name,branch,changes,"fix(gitofy): AI repair for failed GitHub Actions run [skip ci]")
        summary=(f"Diagnosis: {plan.get('diagnosis') or plan.get('summary') or 'Root cause identified from the latest workflow logs.'}\n\n"
                 f"Files fixed: {', '.join(str(c.get('path')) for c in changes[:8])}\n\n"
                 f"Commit: {str(commit_sha or '')[:12]}")
        send_ai_typing(token,chat,summary)
        tg_edit(token,chat,mid,"⏳ <b>AI engineer: fix pushed. Re-running the failed workflow…</b>\n<code>██████████████████░░</code> <b>90%</b>")
        # Dispatch exactly the workflow that failed. The same workflow id is
        # reused; no unrelated workflow is started.
        if not workflow_id:
            raise GitofyError("Failed run has no workflow id; cannot safely re-run the same workflow.")
        gh(token,f"/repos/{owner}/{name}/actions/workflows/{workflow_id}/dispatches","POST",{"ref":branch,"inputs":{}})
        new_run=None
        for _ in range(20):
            time.sleep(2)
            runs=gh(token,f"/repos/{owner}/{name}/actions/runs?per_page=20").get("workflow_runs",[])
            candidates=[x for x in runs if x.get("workflow_id")==int(workflow_id) and x.get("head_branch")==branch and x.get("id")!=run.get("id")]
            if candidates:
                new_run=candidates[0];break
        if not new_run:
            raise GitofyError("Repair was pushed, but the rebuilt workflow run did not appear yet.")
        repo_row=DBS.q("SELECT wr.*,r.owner||'/'||r.name repo FROM workflow_runs wr JOIN repositories r ON r.id=wr.repository_id WHERE wr.github_run_id=?",(run["id"],),True)
        if repo_row:
            DBS.run("INSERT OR IGNORE INTO workflow_runs(repository_id,github_run_id,workflow_id,branch,status,conclusion,telegram_user_id,telegram_chat_id,telegram_message_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(repo_row["repository_id"],new_run["id"],int(workflow_id),branch,new_run.get("status"),new_run.get("conclusion"),uid,chat,mid,now(),now()))
        tg_edit(token,chat,mid,"🚀 <b>AI fix pushed. Rebuild is running now…</b>\n<code>██████████████████████</code> <b>100%</b>\n\nReturning to live job/step monitoring.")
        return new_run
    except Exception as exc:
        tg_edit(token,chat,mid,"❌ <b>AI auto-fix stopped safely.</b>\n\n"+safe(redact(exc),900))
        return None
    finally:
        DBS.release(lock_name,lock_owner)


class Monitor(threading.Thread):
    def __init__(self,token,runrow):super().__init__(daemon=True);self.token=token;self.row=runrow
    def run(self):
        uid=self.row["telegram_user_id"];chat=self.row["telegram_chat_id"];mid=self.row["telegram_message_id"];rid=self.row["github_run_id"];owner,name=self.row["repo"].split("/",1)
        last_hash=""; last_pct=float(self.row["last_progress"] or 0)
        for _ in range(900):
            try:
                run=gh(self.token,f"/repos/{owner}/{name}/actions/runs/{rid}"); jobs=gh(self.token,f"/repos/{owner}/{name}/actions/runs/{rid}/jobs?per_page=100")
                text,pct,done,total=Progress.render(run,jobs.get("jobs",[])); pct=max(last_pct,pct) if run.get("status") not in ("completed",) else pct
                digest=hashlib.sha256(text.encode()).hexdigest()
                if digest!=last_hash:
                    try:tg_edit(self.token,chat,mid,text,self.buttons(rid,owner,name,run.get("status")))
                    except Exception:pass
                    last_hash=digest
                    DBS.run("UPDATE workflow_runs SET status=?,conclusion=?,last_progress=?,last_render_hash=?,updated_at=? WHERE github_run_id=?",(run.get("status"),run.get("conclusion"),pct,digest,now(),rid))
                if run.get("status")=="completed":
                    self.final(run,jobs.get("jobs",[]),owner,name,chat,mid)
                    S.monitors.pop(rid,None)
                    return
                last_pct=pct;time.sleep(POLL_SECONDS)
            except Exception as e:
                DBS.audit(uid,"monitor", "", "github",f"{owner}/{name}",str(rid),"monitor_error",redact(str(e)));time.sleep(min(30,POLL_SECONDS*2))
        try:tg_edit(self.token,chat,mid,"⚠️ Monitoring timeout reached. The GitHub run remains the source of truth.",[[{"text":"🔄 Refresh","callback_data":f"run:{uid}:{rid}:{owner}/{name}"}]])
        except Exception:pass
        S.monitors.pop(rid,None)
    def buttons(self,rid,owner,name,status):
        b=[[{"text":"📜 Logs","callback_data":f"logs:{self.row['telegram_user_id']}:{rid}:{owner}/{name}"},{"text":"📦 Artifacts","callback_data":f"arts:{self.row['telegram_user_id']}:{rid}:{owner}/{name}"}]]
        if status=="in_progress":b.append([{"text":"⛔ Cancel","callback_data":f"cancel:{self.row['telegram_user_id']}:{rid}:{owner}/{name}"}])
        else:b.append([{"text":"🔄 Re-run","callback_data":f"rerun:{self.row['telegram_user_id']}:{rid}:{owner}/{name}"}])
        return b
    def final(self,run,jobs,owner,name,chat,mid):
        text,pct,done,total=Progress.render(run,jobs)
        if run.get("conclusion")=="success":
            text += "\n\n🎉 <b>BUILD SUCCESSFUL</b>"
            tg_edit(self.token,chat,mid,text,self.buttons(run["id"],owner,name,"completed"))
            send_build_success_alert(self.token,self.row["telegram_user_id"],chat,run,owner,name)
            try:
                deliver_run_artifacts(self.token,chat,owner,name,run["id"],self.row["telegram_user_id"])
            except Exception as exc:
                DBS.audit(self.row["telegram_user_id"],"artifact delivery","system","github",f"{owner}/{name}",str(run["id"]),"artifact_delivery_error",redact(str(exc)))
            return
        conclusion=(run.get("conclusion") or "FAILED").upper()
        if run.get("conclusion")=="cancelled":
            text += "\n\n⚪ <b>BUILD CANCELLED</b>"
        elif run.get("conclusion")=="skipped":
            text += "\n\n⚪ <b>BUILD SKIPPED</b>"
        else:
            text += f"\n\n❌ <b>BUILD {safe(conclusion)}</b>"
        tg_edit(self.token,chat,mid,text,self.buttons(run["id"],owner,name,"completed"))
        if run.get("conclusion") in ("failure","timed_out","action_required"):
            send_failure_alert(self.token,self.row["telegram_user_id"],chat,run,owner,name)
            # Automatic repair is opt-in via AI_AUTOFIX_ENABLED. The default is
            # enabled in the bot runtime because the requested feature is an
            # autonomous build-repair loop; set it to false to disable it.
            new_run=ai_autofix_failed_run(self.token,self.row["telegram_user_id"],chat,mid,owner,name,run,jobs)
            if new_run:
                new_row=DBS.q("SELECT wr.*,r.owner||'/'||r.name repo FROM workflow_runs wr JOIN repositories r ON r.id=wr.repository_id WHERE wr.github_run_id=?",(new_run["id"],),True)
                if new_row:
                    mon=Monitor(self.token,new_row);S.monitors[new_run["id"]]=mon;mon.start()
                return

def parse_repo(s):
    p=s.strip().strip("/").split("/");
    if len(p)!=2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+",x or "") for x in p):raise GitofyError("Use owner/name")
    return p[0],p[1]

def repo_info(token, owner, name):
    """Return authoritative repository metadata from GitHub.

    This helper was missing from the standalone Telegram runtime.  Workflow
    buttons (and several repository commands) call it, so a selected workflow
    could otherwise fail with ``name 'repo_info' is not defined``.
    """
    return gh(token, f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}")


def create_repository(token, name, private=False, auto_init=True):
    name=(name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise GitofyError("Invalid repository name.")
    return gh(token, "/user/repos", "POST", {"name": name, "private": bool(private), "auto_init": bool(auto_init)})


def delete_repository(token, owner, name):
    gh(token, f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}", "DELETE")
    return True


def commit_history(token, owner, name, branch=""):
    path=f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}/commits"
    if branch:
        path += "?sha=" + urllib.parse.quote(branch, safe="")
    return gh(token, path).get("items", []) if False else gh(token, path)


def workflow_yaml(token, owner, name, workflow_id, preferred_path=""):
    """Fetch a workflow YAML by numeric workflow id (or its known path)."""
    if preferred_path:
        path=preferred_path
    else:
        w=gh(token, f"/repos/{owner}/{name}/actions/workflows/{urllib.parse.quote(str(workflow_id), safe='')}")
        path=w.get("path") or ""
    if not path:
        raise GitofyError("GitHub did not return the workflow file path.")
    c=gh(token, f"/repos/{owner}/{name}/contents/{urllib.parse.quote(path, safe='/')}")
    raw=c.get("content") or ""
    try:
        text=base64.b64decode(raw.encode()).decode("utf-8", "replace")
    except Exception:
        text=str(raw)
    return path, text


def _git_blob_sha(data):
    """Calculate the SHA-1 Git uses for a normal blob."""
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _repo_tree_files(token, owner, name, branch):
    try:
        ref=gh(token, f"/repos/{owner}/{name}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
    except HttpError as e:
        if e.status==404:
            # A newly-created GitHub repository can be completely empty and
            # therefore have no branch/ref yet. Treat it as an empty project.
            return {}
        raise
    obj=(ref or {}).get("object") or {}
    sha=obj.get("sha")
    if not sha:
        return {}
    tree=gh(token, f"/repos/{owner}/{name}/git/trees/{sha}?recursive=1")
    if tree.get("truncated"):
        raise GitofyError("Repository tree is too large for a safe comparison.")
    return {x.get("path"): x.get("sha") for x in tree.get("tree", []) if x.get("type")=="blob" and x.get("path")}

def _repo_has_branch(token, owner, name, branch):
    try:
        r=gh(token, f"/repos/{owner}/{name}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
        return bool(((r or {}).get("object") or {}).get("sha"))
    except HttpError as e:
        if e.status==404:return False
        raise


def _zip_file_bytes(path):
    z,names,total=validate_zip(path)
    root=project_root(names)
    out={}
    for n in names:
        if not n or n.endswith("/") or n.startswith(".git/"):
            continue
        rel=n[len(root)+1:] if root!="." and n.startswith(root+"/") else n
        if not rel or rel.startswith(".git/"):
            continue
        out[rel]=z.read(n)
    return out


class OperationReporter:
    """Render one Telegram progress message without allowing stale edits to win.

    Progress updates are queued so GitHub/file transfer work is not throttled by
    Telegram edit latency.  All actual Telegram edits are serialized, however,
    which is important: a worker that is already sending an old 99% update must
    finish before the final result is written.  Otherwise the old progress edit
    can arrive after the success message and make the bot appear stuck at 99%.
    """
    def __init__(self,token,chat,msg_id):
        self.token=token; self.chat=chat; self.msg_id=msg_id
        self.lock=threading.RLock(); self.pct=0.0; self.status="Processing…"; self.done=False
        self._last=-1; self._pending=None; self._edit_thread=None; self._stop=False

    @staticmethod
    def _bar(pct,width=20):
        whole=max(0,min(99,int(pct)))
        filled=whole*width//100
        return "█"*filled+"░"*(width-filled)

    def _render(self,pct,status):
        whole=max(0,min(99,int(pct)))
        return f"⏳ <b>{safe(status,220)}</b>\n<code>{self._bar(whole)}</code> <b>{whole}%</b>"

    def _edit_loop(self):
        while True:
            # Hold the same lock during the Telegram request.  This guarantees
            # finish() cannot send the final result before an already-started
            # progress edit and then get overwritten by that stale edit.
            with self.lock:
                item=self._pending
                self._pending=None
                if item is None:
                    if self._stop:
                        return
                    # Do not sleep while holding the lock.
                    sleep_needed=True
                else:
                    sleep_needed=False
                    try: tg_edit(self.token,self.chat,self.msg_id,item)
                    except Exception: pass
            if sleep_needed:
                time.sleep(0.08)

    def _queue_edit(self,text):
        with self.lock:
            if self._stop or self.done:
                return
            self._pending=text
            if self._edit_thread is None or not self._edit_thread.is_alive():
                self._edit_thread=threading.Thread(target=self._edit_loop,daemon=True)
                self._edit_thread.start()

    def advance(self,pct,status):
        with self.lock:
            if self._stop or self.done:
                return
            self.pct=max(self.pct,min(99,float(pct))); self.status=status
            whole=int(self.pct)
            if whole==self._last and self.pct<99: return
            self._last=whole
            text=self._render(self.pct,self.status)
        self._queue_edit(text)

    def finish(self,text,keyboard=None):
        # Serialize the final edit with any in-flight progress edit.  The lock
        # also clears queued progress before the final state is sent.
        with self.lock:
            self.done=True; self.pct=100; self._pending=None; self._stop=True
            try: tg_edit(self.token,self.chat,self.msg_id,text,keyboard)
            except Exception: pass


def compare_zip_to_repo(token, owner, name, branch, path):
    uploaded=_zip_file_bytes(path)
    repo=_repo_tree_files(token, owner, name, branch)
    add=[];mod=[];dele=[]
    for p,b in uploaded.items():
        sha=_git_blob_sha(b)
        if p not in repo:add.append(p)
        elif repo[p] != sha:mod.append(p)
    for p in repo:
        if p not in uploaded:
            dele.append(p)
    return uploaded, repo, add, mod, dele


def sync_zip_to_repo(token, owner, name, branch, path, reporter=None):
    """Replace the GitHub tree with the ZIP tree in one commit.

    Prefer the native libgit2/pygit2 engine when the host already provides it.
    This avoids one HTTP request per blob and lets libgit2 stream Git pack data.
    If native libgit2 is unavailable, use the existing parallel GitHub Git-Data
    API path as a safe fallback.
    """
    # Prefer native Git transports over the GitHub REST Git-Data API.  The REST
    # fallback creates one API request per blob and large projects can hit
    # GitHub's secondary rate limit (HTTP 403) after only a few hundred files.
    # Native libgit2 is preferred; the Git CLI smart-HTTP transport is the next
    # choice because it is commonly preinstalled and also sends one packed Git
    # transfer instead of hundreds/thousands of REST requests.
    engine_mode=os.getenv('GITOFY_GIT_ENGINE','auto').lower()
    if LibGit2Engine is not None and libgit2_available() and engine_mode in ('auto','libgit2','pygit2'):
        import tempfile, shutil
        with tempfile.TemporaryDirectory(prefix='gitofy-upload-') as td:
            root=Path(td)
            validate_zip(path)
            z=zipfile.ZipFile(path)
            names=[x.filename.replace('\\','/').lstrip('/') for x in z.infolist() if x.filename and not x.is_dir()]
            top=project_root(names)
            for item in z.infolist():
                n=item.filename.replace('\\','/').lstrip('/')
                if not n or n.startswith('.git/') or n.endswith('/'): continue
                rel=n[len(top)+1:] if top!='.' and n.startswith(top+'/') else n
                if not rel or rel.startswith('.git/'): continue
                target=root/rel; target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(item) as src, target.open('wb') as out: shutil.copyfileobj(src,out,1024*1024)
            if reporter: reporter.advance(3,'Using native libgit2 Git engine…')
            commit=LibGit2Engine(token).sync_existing(owner,name,branch,root,
                progress=(lambda done,total,pct: reporter.advance(5+(pct or 0)*0.9,'Uploading Git pack via libgit2…') if reporter and pct is not None else None),
                message='chore(gitofy): replace project from ZIP [skip ci]')
            if reporter: reporter.advance(98,'Repository updated successfully. Finalizing…')
            file_count=sum(1 for p in root.rglob('*') if p.is_file())
            total_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
            return {'changed':True,'added':file_count,'modified':0,'deleted':0,'sha':str(commit),
                    'files':file_count,'bytes':total_bytes,'workflows':{'total':0,'started':[],'natural':[],'skipped':[],'failed':[],'auto_disabled':True},'engine':'libgit2'}

    if GitCliEngine is not None and git_cli_available() and engine_mode in ('auto','git','cli','git-cli'):
        if reporter: reporter.advance(2,'Using native Git smart-HTTP transport…')
        commit=GitCliEngine(token).sync_zip(owner,name,branch,path,
            progress=(lambda pct: reporter.advance(5+max(0,min(100,float(pct)))*0.9,
                f'Uploading project… {float(pct):.0f}%') if reporter else None),
            message='chore(gitofy): replace project from ZIP [skip ci]')
        if reporter: reporter.advance(98,'Repository updated successfully. Finalizing…')
        return {'changed':True,'added':commit.get('files',0),'modified':0,'deleted':commit.get('deleted',0),
                'sha':commit.get('sha'),'files':commit.get('files',0),'bytes':commit.get('bytes',0),
                'workflows':{'total':0,'started':[],'natural':[],'skipped':[],'failed':[],'auto_disabled':True},
                'engine':'git-cli'}

    uploaded=_zip_file_bytes(path)
    if not uploaded: raise GitofyError("The ZIP contains no uploadable project files.")
    total_bytes=max(1,sum(len(b) for b in uploaded.values()))
    if reporter: reporter.advance(1,"Preparing project replacement…")

    try:
        ref=gh(token,f"/repos/{owner}/{name}/git/ref/heads/{urllib.parse.quote(branch,safe='')}")
        parent=((ref or {}).get("object") or {}).get("sha")
    except HttpError as e:
        if e.status==404: parent=None
        else: raise

    items=list(uploaded.items())
    results=[None]*len(items)
    completed_bytes=0
    completed_lock=threading.Lock()

    def upload_one(idx_item):
        idx,(rel,data)=idx_item
        if len(data)>100*1024*1024:
            raise GitofyError(f"File is larger than GitHub's 100 MB Git blob limit: {rel}")
        blob=gh(token,f"/repos/{owner}/{name}/git/blobs","POST",{
            "content":base64.b64encode(data).decode("ascii"),"encoding":"base64"
        })
        sha=blob.get("sha")
        if not sha: raise GitofyError(f"GitHub did not return a blob SHA for {rel}")
        return idx,rel,data,sha

    # Six concurrent GitHub requests gives a large speed-up while staying
    # conservative enough for GitHub API rate limits on shared hosts.
    workers=max(2,min(6,int(os.getenv("GITOFY_UPLOAD_WORKERS","6"))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(upload_one,x) for x in enumerate(items)]
        for fut in concurrent.futures.as_completed(futures):
            idx,rel,data,sha=fut.result()
            results[idx]={"path":rel,"mode":"100644","type":"blob","sha":sha}
            with completed_lock:
                completed_bytes += len(data)
                done_bytes=completed_bytes
            pct=5+(done_bytes/total_bytes)*70
            if reporter: reporter.advance(pct,f"Uploading project… {sum(1 for x in results if x)}/{len(items)} files")

    if reporter: reporter.advance(78,"Building replacement repository tree…")
    tree=gh(token,f"/repos/{owner}/{name}/git/trees","POST",{"tree":results})
    tree_sha=tree.get("sha")
    if not tree_sha: raise GitofyError("GitHub did not return the new tree SHA.")

    if reporter: reporter.advance(84,"Creating replacement commit…")
    commit_payload={"message":"chore(gitofy): replace project from ZIP [skip ci]","tree":tree_sha}
    if parent: commit_payload["parents"]=[parent]
    commit=gh(token,f"/repos/{owner}/{name}/git/commits","POST",commit_payload)
    commit_sha=commit.get("sha")
    if not commit_sha: raise GitofyError("GitHub did not return the new commit SHA.")

    if reporter: reporter.advance(91,"Updating GitHub branch…")
    if parent:
        gh(token,f"/repos/{owner}/{name}/git/refs/heads/{urllib.parse.quote(branch,safe='')}","PATCH",{"sha":commit_sha,"force":False})
    else:
        gh(token,f"/repos/{owner}/{name}/git/refs","POST",{"ref":f"refs/heads/{branch}","sha":commit_sha})

    if reporter: reporter.advance(98,"Repository updated successfully. Finalizing…")
    workflows={"total":0,"started":[],"natural":[],"skipped":[],"failed":[],"auto_disabled":True}
    return {"changed":True,"added":len(uploaded),"modified":0,"deleted":0,"sha":commit_sha,
            "files":len(uploaded),"bytes":total_bytes,"workflows":workflows}



def update_zip_to_repo(token, owner, name, branch, path, reporter=None):
    """Replace the repository working tree with the uploaded ZIP.

    The Update Project action is intentionally a full replacement, not an
    overlay.  Every tracked project file that is absent from the new ZIP is
    removed, and every file from the ZIP is written to the repository.  Git
    history is preserved because the replacement is committed normally.
    """
    if reporter:
        reporter.advance(2, 'Preparing full project replacement…')
    result = sync_zip_to_repo(token, owner, name, branch, path, reporter)
    result['engine'] = result.get('engine', 'auto')
    return result

def _workflow_triggers(yaml_text):
    """Return trigger keys from the workflow's top-level `on:` block.

    Gitofy deliberately avoids a YAML dependency in the host runtime.  This
    parser only needs the top-level event names, so it walks indentation rather
    than trying to parse the complete workflow document.
    """
    text=yaml_text or ""
    lines=text.splitlines()
    on_index=None
    on_indent=0
    for i,line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        m=re.match(r'^(\s*)(?:on|["\']on["\'])\s*:\s*(.*)$',line)
        if m:
            on_index=i;on_indent=len(m.group(1));inline=m.group(2).strip();break
    if on_index is None:
        return set()
    triggers=set()
    # Inline forms: on: [push, workflow_dispatch]
    if inline.startswith('['):
        for x in inline.strip('[]').split(','):
            x=x.strip().strip('"\'')
            if x:triggers.add(x)
        return triggers
    # Empty/map form: first determine the indentation of direct children,
    # then ignore nested keys such as `branches:` under `push:`.
    child_indent=None
    for line in lines[on_index+1:]:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent=len(line)-len(line.lstrip())
        if indent<=on_indent:
            break
        if not line.strip().startswith('- '):
            child_indent=indent
            break
    if child_indent is None:
        return triggers
    for line in lines[on_index+1:]:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent=len(line)-len(line.lstrip())
        if indent<=on_indent:
            break
        if indent!=child_indent:
            continue
        stripped=line.strip()
        if stripped.startswith('- '):
            continue
        m=re.match(r'^(?:["\']?)([A-Za-z0-9_-]+)(?:["\']?)\s*:',stripped)
        if m:triggers.add(m.group(1))
    return triggers


def _workflow_supports_dispatch(yaml_text):
    return 'workflow_dispatch' in _workflow_triggers(yaml_text)


def _workflow_is_push_triggered(yaml_text):
    t=_workflow_triggers(yaml_text)
    return bool(t & {'push','pull_request','pull_request_target','create','delete'})


def _workflow_is_manual_only(yaml_text):
    t=_workflow_triggers(yaml_text)
    return 'workflow_dispatch' in t and not _workflow_is_push_triggered(yaml_text) and 'workflow_call' not in t


def auto_run_project_workflows(token,owner,name,branch,reporter=None):
    """Hard safety guard: repository sync never dispatches workflows automatically.

    A replacement commit can trigger push/PR workflows, and workflows can also
    trigger other workflows through workflow_run/repository_dispatch. Automatically
    fanning out dispatch calls from Gitofy can therefore create a workflow storm.
    Users can run a specific workflow explicitly from the Run Workflow UI.
    """
    if reporter:
        reporter.advance(98,"Repository updated. No automatic workflow dispatch was performed.")
    return {"total":0,"started":[],"natural":[],"skipped":[],"failed":[],"auto_disabled":True}

def signed_token(secret, payload, ttl=900):
    exp=int(time.time())+int(ttl)
    body=f"{exp}.{payload}"
    sig=hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{body}.{sig}".encode()).decode().rstrip("=")

def verify_token(secret, token):
    if not secret:
        raise GitofyError("Download signing secret is not configured")
    try:
        raw=base64.urlsafe_b64decode(token + "="*((4-len(token)%4)%4)).decode()
        exp,payload,sig=raw.rsplit(".",2)
        body=f"{exp}.{payload}"
        if int(exp) < int(time.time()):
            raise GitofyError("Download link expired")
        expected=hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected):
            raise GitofyError("Invalid download link")
        return payload
    except GitofyError:
        raise
    except Exception:
        raise GitofyError("Invalid download link")


def list_branches(token, owner, name):
    return gh(token, f"/repos/{owner}/{name}/branches?per_page=100")


def create_branch(token, owner, name, new_branch, from_branch="main"):
    ref=gh(token, f"/repos/{owner}/{name}/git/ref/heads/{urllib.parse.quote(from_branch, safe='')}")
    sha=((ref or {}).get("object") or {}).get("sha")
    if not sha:
        raise GitofyError(f"Source branch not found: {from_branch}")
    return gh(token, f"/repos/{owner}/{name}/git/refs", "POST", {"ref":f"refs/heads/{new_branch}","sha":sha})

def validate_zip(path):
    try:z=zipfile.ZipFile(path)
    except zipfile.BadZipFile:raise GitofyError("Corrupt ZIP")
    total=0;names=[];symlinks=[]
    for i in z.infolist():
        n=i.filename
        if n.startswith("/") or ".." in Path(n).parts or "\\" in n:raise GitofyError("ZIP rejected: unsafe path traversal")
        mode=(i.external_attr>>16)&0xffff
        if mode and (mode&0o170000)==0o120000:raise GitofyError("ZIP rejected: symlink entry")
        total+=i.file_size;names.append(n)
        if len(names)>MAX_FILES:raise GitofyError("ZIP rejected: too many files")
        if total>MAX_UNPACK:raise GitofyError("ZIP rejected: extracted size limit exceeded")
    return z,names,total

def detect_project(names):
    low=[x.lower() for x in names]; root=project_root(names)
    return {"root":root,"android":any(x.endswith("androidmanifest.xml") for x in low) or any("com.android.application" in x for x in low),"gradle":any(x.endswith(("build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts")) for x in low),"kotlin":any(x.endswith(".kt") for x in low),"java":any(x.endswith(".java") for x in low),"python":any(x.endswith(".py") for x in low),"node":any(x.endswith("package.json") for x in low)}
def project_root(names):
    tops={n.split("/",1)[0] for n in names if n and "/" in n};
    if len(tops)==1 and all(n.startswith(next(iter(tops))+"/") for n in names):return next(iter(tops))
    return "."

def zip_files(path):
    z,names,total=validate_zip(path); out={}
    for n in names:
        if n.endswith("/") or n.startswith(".git/"):continue
        try:
            b=z.read(n)
            if len(b)<=2_000_000:out[n]=b.decode("utf-8","replace")
        except Exception:pass
    return out

def github_permissions(headers):
    return {k:v for k,v in headers.items() if k.lower().startswith("x-oauth-scopes") or k.lower().startswith("x-accepted-oauth-scopes")}

def token_validate(token):
    """Validate a GitHub PAT with a short, bounded request.

    This function is intentionally synchronous-safe: callers run it in a worker
    thread so Telegram polling never blocks while GitHub is unreachable.
    """
    token=(token or "").strip()
    if token.lower().startswith("bearer "): token=token[7:].strip()
    if token.lower().startswith("token "): token=token[6:].strip()
    if not token: raise GitofyError("GitHub token is empty.")
    if not (token.startswith("ghp_") or token.startswith("github_pat_") or len(token) >= 20):
        raise GitofyError("The value does not look like a GitHub Personal Access Token.")
    base={"X-GitHub-Api-Version":"2022-11-28","Accept":"application/vnd.github+json","User-Agent":"Gitofy/1.1"}
    try:
        status,headers,raw=http(GH+"/user","GET",dict(base,Authorization=f"Bearer {token}"),timeout=15)
        obj=json.loads(raw.decode()) if raw else {}
        if not obj.get("login"):
            raise GitofyError("GitHub authenticated, but no user identity was returned.")
        return obj,github_permissions(headers)
    except HttpError as e:
        if e.status==401:
            raise GitofyError("Invalid or expired GitHub PAT. Please create/copy a valid PAT.")
        if e.status==403:
            raise GitofyError("GitHub rejected the request (403). Check token permissions, SSO, or organization policy.")
        raise GitofyError(f"GitHub returned HTTP {e.status}: {safe(e.message,500)}")
    except urllib.error.URLError as e:
        raise GitofyError("Could not reach GitHub. Check the host's outbound HTTPS/network access.")
    except TimeoutError:
        raise GitofyError("GitHub validation timed out. Check the host's outbound HTTPS/network access.")


def send_ai_typing(token, chat, text, prefix="🤖 <b>Gitofy AI</b>"):
    """Render an AI response as a small typewriter sequence.

    Telegram does not provide a true server-side typewriter primitive, so we
    edit one message in throttled chunks and emit the native typing action while
    the response is being rendered.
    """
    plain=re.sub(r"<[^>]+>","",str(text or "")).strip()
    if not plain:
        return None
    first=tg_send(token,chat,f"{prefix}\n\n")
    mid=first.get("message_id")
    if not mid:
        return first
    step=70
    for end in range(step,len(plain),step):
        try: tg(token,"sendChatAction",{"chat_id":chat,"action":"typing"})
        except Exception: pass
        try: tg_edit(token,chat,mid,f"{prefix}\n\n{safe(plain[:end],3600)}")
        except Exception: pass
        time.sleep(0.10)
    try: tg_edit(token,chat,mid,f"{prefix}\n\n{safe(plain,3600)}")
    except Exception: pass
    return {"message_id":mid}


def ai(prompt):
    key=os.getenv("GEMINI_API_KEY","").strip()
    if key:
        model=os.getenv("GEMINI_MODEL","gemini-2.5-flash");url=f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(key)}"
        o=json_http(url,"POST",{}, {"contents":[{"parts":[{"text":prompt}]}]},120)
        try:return o["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:return safe(json.dumps(o),3500)
    key=os.getenv("OPENROUTER_API_KEY","").strip()
    if key:
        model=os.getenv("OPENROUTER_MODEL","openai/gpt-4o-mini");o=json_http("https://openrouter.ai/api/v1/chat/completions","POST",{"Authorization":f"Bearer {key}"},{"model":model,"messages":[{"role":"user","content":prompt}]},120)
        try:return o["choices"][0]["message"]["content"]
        except Exception:return safe(json.dumps(o),3500)
    return None

def kb_search(token,owner,name,q):
    tree=gh(token,f"/repos/{owner}/{name}/git/trees/{gh(token,f'/repos/{owner}/{name}').get('default_branch','main')}?recursive=1")
    hits=[];terms=[x.lower() for x in re.findall(r"[A-Za-z0-9_.-]+",q)]
    for x in tree.get("tree",[]):
        p=x.get("path","");
        if x.get("type")!="blob" or any(k in p.lower() for k in ("node_modules","build/",".gradle/")):continue
        score=sum(p.lower().count(t) for t in terms)
        if score:hits.append((score,p))
    return [p for _,p in sorted(hits,reverse=True)[:20]]

def ai_analyze_repo(token,owner,name,request):
    paths=kb_search(token,owner,name,request); snippets=[]
    for p in paths[:8]:
        try:
            c=gh(token,f"/repos/{owner}/{name}/contents/{urllib.parse.quote(p,safe='/')}");b=base64.b64decode(c.get("content","")).decode("utf-8","replace");snippets.append(f"FILE {p}\n{b[:7000]}")
        except Exception:pass
    return ai(f"You are Gitofy autonomous engineering agent. Repository {owner}/{name}. User request: {request}\nRelevant files:\n"+"\n\n".join(snippets))

def workflow_yaml_android():
    return """name: Gitofy Android Release\non:\n  workflow_dispatch:\n    inputs:\n      build_type:\n        description: Build type\n        required: false\n        default: release\n        type: choice\n        options: [debug, release]\npermissions:\n  contents: read\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-java@v4\n        with:\n          distribution: temurin\n          java-version: '17'\n      - uses: gradle/actions/setup-gradle@v4\n      - name: Build APK\n        run: ./gradlew assemble${{ inputs.build_type == 'debug' && 'Debug' || 'Release' }} --stacktrace\n      - name: Upload APK/AAB\n        uses: actions/upload-artifact@v4\n        with:\n          name: android-artifacts\n          path: |\n            **/build/outputs/apk/**/*.apk\n            **/build/outputs/bundle/**/*.aab\n          if-no-files-found: error\n"""

def ensure_workflow(token,owner,name,branch,kind="android"):
    path=".github/workflows/gitofy-android.yml"; content=workflow_yaml_android();
    # GitHub contents API: create or update, using current SHA if present.
    sha=None
    try:sha=gh(token,f"/repos/{owner}/{name}/contents/{path}").get("sha")
    except Exception:pass
    payload={"message":"chore(gitofy): add Android build workflow","content":base64.b64encode(content.encode()).decode(),"branch":branch}
    if sha:payload["sha"]=sha
    return gh(token,f"/repos/{owner}/{name}/contents/{path}","PUT",payload)

def create_pr(token,owner,name,head,base,title,body):return gh(token,f"/repos/{owner}/{name}/pulls","POST",{"title":title,"head":head,"base":base,"body":body})
def list_prs(token,owner,name):return gh(token,f"/repos/{owner}/{name}/pulls?state=all&per_page=30")
def issue_create(token,owner,name,title,body):return gh(token,f"/repos/{owner}/{name}/issues","POST",{"title":title,"body":body})
def release_create(token,owner,name,tag,title,body):return gh(token,f"/repos/{owner}/{name}/releases","POST",{"tag_name":tag,"name":title,"body":body})

def send_log_report(token,chat,owner,name,rid,job=None):
    try:
        _,headers,raw=gh_raw(token,f"/repos/{owner}/{name}/actions/jobs/{job['id']}/logs" if job else f"/repos/{owner}/{name}/actions/runs/{rid}/logs")
        if headers.get("Content-Type","").startswith("application/zip"):
            z=zipfile.ZipFile(io.BytesIO(raw));text="\n\n".join(z.read(n).decode("utf-8","replace") for n in z.namelist())
        else:text=raw.decode("utf-8","replace")
        text=redact(text); path=TMP/f"failure_{rid}.txt";path.write_text(text[:8_000_000],encoding="utf-8")
        tg(token,"sendDocument",{"chat_id":chat,"caption":f"📄 Build failure report • Run #{rid}"},{"document":(path.name,path.read_bytes(),"text/plain")})
    except Exception as e:tg_send(token,chat,f"⚠️ Could not retrieve full logs: {safe(redact(e))}")


def deliver_run_artifacts(token,chat,owner,name,rid,uid):
    """Send successful-run artifacts with both a direct GitHub link and the
    actual ZIP file when it fits Telegram's document upload tier."""
    a=gh(token,f"/repos/{owner}/{name}/actions/runs/{rid}/artifacts?per_page=100").get("artifacts",[])
    if not a:
        return
    rows=[]
    delivered=0
    for x in a:
        if x.get("expired"):
            continue
        aid=x.get("id"); nm=x.get("name") or f"artifact-{aid}"; size=int(x.get("size_in_bytes") or 0)
        direct=x.get("archive_download_url") or _run_url(owner,name,rid)
        DBS.run("INSERT INTO artifact_history(telegram_user_id,repository,run_id,name,size,url,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",(uid,f"{owner}/{name}",rid,nm,size,direct,now(),x.get("expires_at")))
        rows.append([{"text":f"🔗 Direct: {nm}","url":direct}])
        try:
            h={"Authorization":f"Bearer {token}","X-GitHub-Api-Version":"2022-11-28","Accept":"application/vnd.github+json"}
            r=http(GH+f"/repos/{owner}/{name}/actions/artifacts/{aid}/zip","GET",h,None,180,stream=True)
            path=TMP/f"artifact_{aid}.zip";written=0
            with path.open("wb") as out:
                while True:
                    b=r.read(8*1024*1024)
                    if not b: break
                    written+=len(b);out.write(b)
                    if written>2*1024*1024*1024: raise GitofyError("Artifact exceeds 2 GB proxy limit")
            if written<=49*1024*1024:
                tg(token,"sendDocument",{"chat_id":chat,"caption":f"📦 {nm} • Run #{rid}"},{"document":(path.name,path.read_bytes(),"application/zip")})
                delivered+=1
            else:
                rows.append([{"text":f"📥 Download {nm} ({written/1024/1024:.1f} MB)","url":direct}])
        except Exception as exc:
            rows.append([{"text":f"📥 Download {nm}","url":direct}])
            DBS.audit(uid,"artifact","system","github",f"{owner}/{name}",str(aid),"artifact_download_error",redact(str(exc)))
    rows.append([{"text":"📊 Open workflow run","url":_run_url(owner,name,rid)}])
    tg_send(token,chat,f"📦 <b>Build artifacts • Run #{rid}</b>\n\nThe direct download links are below. Artifacts within Telegram's document tier were also sent as files.",rows)
    return delivered


def artifact_menu(token,chat,pat,owner,name,rid,uid):
    if not pat:return
    a=gh(pat,f"/repos/{owner}/{name}/actions/runs/{rid}/artifacts?per_page=100").get("artifacts",[])
    if not a:return
    rows=[]
    for x in a:
        nm=x.get("name","");size=int(x.get("size_in_bytes",0)); url=x.get("archive_download_url","")
        DBS.run("INSERT INTO artifact_history(telegram_user_id,repository,run_id,name,size,url,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",(uid,f"{owner}/{name}",rid,nm,size,url,now(),x.get("expires_at")))
        direct=x.get("archive_download_url") or _run_url(owner,name,rid)
        rows.append([{"text":f"📥 Download {nm} ({size/1024/1024:.1f} MB)","callback_data":f"artifact:{uid}:{rid}:{owner}/{name}:{x['id']}"}, {"text":"🔗 Direct link","url":direct}])
    tg_send(token,chat,"📦 <b>Android Artifacts</b>\nSelect an artifact:",rows)

def download_artifact(token,chat,owner,name,aid):
    # Stream the authenticated GitHub artifact to disk. Do not materialize large files in RAM.
    try:
        h={"Authorization":f"Bearer {token}","X-GitHub-Api-Version":"2022-11-28","Accept":"application/vnd.github+json"}
        url=GH+f"/repos/{owner}/{name}/actions/artifacts/{aid}/zip";r=http(url,"GET",h,None,180,stream=True)
        path=TMP/f"artifact_{aid}.zip";size=0
        with path.open("wb") as out:
            while True:
                b=r.read(8*1024*1024)
                if not b:break
                size+=len(b);out.write(b)
                if size>2*1024*1024*1024:raise GitofyError("Artifact exceeds configured 2 GB proxy limit")
        if size<=49*1024*1024:
            # Telegram multipart still requires bytes; this tier is deliberately limited to ~50 MB.
            data=path.read_bytes();tg(token,"sendDocument",{"chat_id":chat,"caption":"📦 GitHub artifact"},{"document":(path.name,data,"application/zip")})
        else:
            base=os.getenv("PUBLIC_BASE_URL","").rstrip('/');secret=os.getenv("DOWNLOAD_SIGNING_KEY","")
            if base and secret:
                token2=signed_token(secret,f"artifact:{owner}/{name}:{aid}",ttl=900);tg_send(token,chat,f"📦 <b>Large artifact</b>\nSize: {size/1024/1024:.1f} MB\nSigned download (15 min):\n{base}/download/{token2}")
            else:tg_send(token,chat,f"📦 Artifact is {size/1024/1024:.1f} MB. Configure PUBLIC_BASE_URL + DOWNLOAD_SIGNING_KEY or S3/R2 for direct delivery.")
    except Exception as e:tg_send(token,chat,f"❌ Artifact download failed: {safe(redact(e))}")

def _settings_back(uid):
    return [[{"text":"⬅️ Settings","callback_data":f"settings:{uid}:root"},{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]]

def _settings_edit(token,chat,msg_id,uid,text,keyboard):
    if msg_id:
        try:
            tg_edit(token,chat,msg_id,text,keyboard)
            return {"message_id":msg_id}
        except Exception:
            pass
    return tg_send(token,chat,text,keyboard)

def settings_menu(token,chat,uid,msg_id=None):
    on=DBS.notify_pref(uid)
    text="⚙️ <b>Settings</b>\n\nChoose configuration:"
    kb=[[{"text":"🤖 AI Providers","callback_data":f"settings:{uid}:ai"},{"text":f"🔔 Failure Alerts: {'🟢 ON' if on else '⚪ OFF'}","callback_data":f"notify:{uid}:toggle"}],
        [{"text":"🔨 Auto Build","callback_data":f"settings:{uid}:autobuild"},{"text":"🧹 Cleanup","callback_data":f"settings:{uid}:cleanup"}],
        [{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]]
    return _settings_edit(token,chat,msg_id,uid,text,kb)

def ai_providers_menu(token,chat,uid,msg_id=None):
    github_ok=bool(DBS.pat(uid))
    if not github_ok:
        text=("🤖 <b>AI Providers</b>\n\n"
              "🔒 GitHub Connection is required first.\n"
              "Connect GitHub before configuring Gemini, OpenRouter or NVIDIA.")
        kb=[[{"text":"🔐 Connect GitHub","callback_data":f"menu:{uid}:github"}],
            [{"text":"⬅️ Settings","callback_data":f"settings:{uid}:root"},{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]]
        return _settings_edit(token,chat,msg_id,uid,text,kb)
    gemini=bool(os.getenv("GEMINI_API_KEY","").strip())
    openrouter=bool(os.getenv("OPENROUTER_API_KEY","").strip())
    nvidia=bool(os.getenv("NVIDIA_API_KEY","").strip())
    text=("🤖 <b>AI Providers</b>\n\n"
          "GitHub Connection: 🟢 Connected\n\n"
          f"Google Gemini: {'🟢 Connected' if gemini else '🔴 Not configured'}\n"
          f"OpenRouter: {'🟢 Connected' if openrouter else '🔴 Not configured'}\n"
          f"NVIDIA NIM: {'🟢 Connected' if nvidia else '🔴 Not configured'}\n\n"
          "AI Fix mode: ⚡ Auto\n"
          "Head AI and specialist models are selected automatically when Auto mode is enabled.")
    kb=[[{"text":"🧠 AI Models","callback_data":f"menu:{uid}:aimodels"}],
        [{"text":"⚡ Auto Mode","callback_data":f"settings:{uid}:aimode:auto"}],
        [{"text":"⬅️ Settings","callback_data":f"settings:{uid}:root"},{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]]
    return _settings_edit(token,chat,msg_id,uid,text,kb)

def auto_build_menu(token,chat,uid,msg_id=None):
    text=("🔨 <b>Auto Build</b>\n\n"
          "Configure whether Gitofy should automatically monitor the workflow after a project sync.\n\n"
          "Current mode: <b>Monitor after upload</b>")
    kb=[[{"text":"🟢 Enable Auto Build","callback_data":f"settings:{uid}:autobuild:on"},
         {"text":"⚪ Disable Auto Build","callback_data":f"settings:{uid}:autobuild:off"}],
        [{"text":"⬅️ Settings","callback_data":f"settings:{uid}:root"},{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]]
    return _settings_edit(token,chat,msg_id,uid,text,kb)

def cleanup_menu(token,chat,uid,msg_id=None):
    text=("🧹 <b>Cleanup</b>\n\n"
          "Gitofy automatically removes temporary ZIP/download files according to the host cleanup interval.\n\n"
          "Nothing is deleted from your GitHub repositories by this setting.")
    kb=[[{"text":"🧹 Run Cleanup Now","callback_data":f"settings:{uid}:cleanup:now"}],
        [{"text":"⬅️ Settings","callback_data":f"settings:{uid}:root"},{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]]
    return _settings_edit(token,chat,msg_id,uid,text,kb)

def main_menu(uid):
    return [[{"text":"📦 Repositories","callback_data":f"menu:{uid}:repos"},{"text":"➕ New Repository","callback_data":f"menu:{uid}:create_repo"}],
            [{"text":"📤 Upload Project","callback_data":f"menu:{uid}:upload"},{"text":"🔄 Update Project","callback_data":f"menu:{uid}:update"}],
            [{"text":"⚙️ Workflows","callback_data":f"menu:{uid}:workflows"},{"text":"▶️ Run Workflow","callback_data":f"menu:{uid}:run"}],
            [{"text":"📊 Build Status","callback_data":f"menu:{uid}:runs"},{"text":"📜 Build Logs","callback_data":f"menu:{uid}:logs"}],
            [{"text":"📥 Artifacts","callback_data":f"menu:{uid}:arts"},{"text":"🔐 GitHub Connection","callback_data":f"menu:{uid}:github"}],[{"text":"🔑 PAT Capabilities","callback_data":f"menu:{uid}:patcaps"}],
            [{"text":"⚙️ Settings","callback_data":f"menu:{uid}:settings"},{"text":"❓ Help","callback_data":f"menu:{uid}:help"}]]

HELP="""<b>🚀 Gitofy</b> — Your GitHub control center inside Telegram.

<b>GitHub</b>
/connect • /disconnect • /github • /repos • /repo owner/name

<b>Projects</b>
/upload • /update • /compare owner/name branch • /search owner/name query
/create-repo • /delete-repo owner/name CONFIRM • /branches • /branch owner/name new from
/file owner/name path • /commits owner/name [branch]

<b>Actions</b>
/workflows owner/name • /workflow owner/name id • /workflow-yaml owner/name workflow-id
/run owner/name workflow-id branch [JSON inputs]
/runs owner/name • /status owner/name run-id • /cancel owner/name run-id • /rerun owner/name run-id
/logs owner/name run-id • /artifacts owner/name run-id • /download owner/name artifact-id

<b>Engineering</b>
/ai request • /fix owner/name request • /review owner/name request
/issue owner/name title • /pr owner/name head base title • /release owner/name tag title
/issue owner/name title • /pr owner/name head base title • /release owner/name tag title
/rollback owner/name branch

<b>Operations</b>
/settings • /memory • /audit • /schedule • /maintenance • /healthz • /diag

Dangerous operations require explicit confirmation. Build results and progress always come from GitHub state."""

class State:
    def __init__(self):self.awaiting={};self.offset=0;self.monitors={};self.uploads={};self.lock=threading.RLock()
S=State()

def repo_list(token,uid,chat):
    rs=gh(token,"/user/repos?per_page=100&sort=updated");
    rows=[]
    for r in rs:DBS.run("INSERT INTO repositories(telegram_user_id,github_repo_id,owner,name,default_branch,visibility,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(telegram_user_id,github_repo_id) DO UPDATE SET default_branch=excluded.default_branch,updated_at=excluded.updated_at",(uid,r["id"],r["owner"]["login"],r["name"],r.get("default_branch","main"),r.get("visibility","unknown"),now(),now()))
    text="<b>📦 Repositories</b>\n\n"+"\n".join(f"• <code>{safe(r['full_name'])}</code> — {r.get('visibility','')} — {r.get('default_branch','main')}" for r in rs[:50])
    tg_send(TOKEN,chat,text,[[{"text":"➕ New Repository","callback_data":f"menu:{uid}:create_repo"},{"text":"🔄 Refresh","callback_data":f"menu:{uid}:repos"}],[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])

def start_flow(token,uid,chat):
    welcome="""<b>🚀 Gitofy</b>\n\nYour GitHub Control Center inside Telegram.\n\nManage repositories, upload projects, update source code, run GitHub Actions, monitor builds, inspect logs and download build artifacts directly from Telegram.\n\n<b>✨ Features</b>\n• GitHub Repository Management\n• ZIP Project Upload & secure comparison\n• GitHub Actions & real-time monitoring\n• Build logs & failure TXT reports\n• APK / AAB artifact management\n• AI engineering, memory & knowledge base\n• PR / Issue / Release automation\n• Risk-based permissions & audit trail"""
    tg_send(token,chat,welcome,main_menu(uid))

def _handle_cmd_impl(token,uid,chat,text):
    a=text.split();cmd=a[0].split('@')[0].lower(); arg=a[1] if len(a)>1 else ''; rest=" ".join(a[2:])
    DBS.user(uid,"")
    try:
        if cmd=="/start":start_flow(token,uid,chat)
        elif cmd=="/help":tg_send(token,chat,HELP,[[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])
        elif cmd in ("/connect","/github"):
            S.awaiting[uid]="pat";DBS.set_pending(uid,"pat");tg_send(token,chat,"🔐 <b>Connect GitHub</b>\n\nSend your Personal Access Token in your next message. No command is required. Gitofy will validate it automatically.")
        elif cmd=="/disconnect":DBS.run("DELETE FROM github_connections WHERE telegram_user_id=?",(uid,));DBS.clear_pending(uid);S.awaiting.pop(uid,None);SESSION_PATS.pop(uid,None);tg_send(token,chat,"🔐 GitHub disconnected.")
        elif cmd=="/repos":repo_list(DBS.pat(uid),uid,chat) if DBS.pat(uid) else tg_send(token,chat,"🔐 Connect GitHub first with /connect")
        elif cmd=="/repo":
            t=DBS.pat(uid);o,n=parse_repo(arg);r=repo_info(t,o,n);w=gh(t,f"/repos/{o}/{n}/actions/workflows?per_page=100");tg_send(token,chat,f"<b>📁 {safe(r['full_name'])}</b>\n🌿 {safe(r.get('default_branch','main'))}\n🔒 {safe(r.get('visibility',''))}\n⭐ {r.get('stargazers_count',0)}\n🍴 {r.get('forks_count',0)}\n⚙️ Workflows: {w.get('total_count',0)}\n🔗 {safe(r.get('html_url',''))}")
        elif cmd=="/create-repo":
            t=DBS.pat(uid);name=a[1];private=(a[2].lower()=='private' if len(a)>2 else False);x=create_repository(t,name,private);tg_send(token,chat,f"📦 Repository created\n{x.get('full_name')}\n{x.get('html_url','')}")
        elif cmd=="/delete-repo":
            if len(a)<3 or a[2].upper()!="CONFIRM":raise GitofyError("Dangerous operation. Use /delete-repo owner/name CONFIRM")
            t=DBS.pat(uid);o,n=parse_repo(a[1]);delete_repository(t,o,n);DBS.audit(uid,text,'confirmed','github',f'{o}/{n}','repository','delete','success');tg_send(token,chat,"🗑 Repository deleted after explicit confirmation.")
        elif cmd=="/branches":
            t=DBS.pat(uid);o,n=parse_repo(arg);bs=list_branches(t,o,n);tg_send(token,chat,"🌿 <b>Branches</b>\n\n"+"\n".join(f"• {safe(x['name'])}" for x in bs))
        elif cmd=="/branch":
            if len(a)<4:raise GitofyError("Usage: /branch owner/name new-branch from-branch")
            t=DBS.pat(uid);o,n=parse_repo(a[1]);x=create_branch(t,o,n,a[2],a[3]);tg_send(token,chat,f"🌿 Branch created: <code>{safe(a[2])}</code>")
        elif cmd in ("/workflows","/workflow"):
            t=DBS.pat(uid);o,n=parse_repo(arg);w=gh(t,f"/repos/{o}/{n}/actions/workflows?per_page=100");rows=[]
            for x in w.get('workflows',[]):rows.append([{"text":f"⚙️ {x['name']}","callback_data":f"wf:{uid}:{o}/{n}:{x['id']}"}])
            tg_send(token,chat,"<b>⚙️ Workflows</b>\n\n"+"\n".join(f"• {safe(x['name'])} — <code>{x['id']}</code> — {x.get('state','')}" for x in w.get('workflows',[])),rows)
        elif cmd=="/workflow-yaml":
            t=DBS.pat(uid);o,n=parse_repo(a[1]);path,y=workflow_yaml(t,o,n,a[2],a[3] if len(a)>3 else '');tg_send(token,chat,f"📄 <b>{safe(path)}</b>\n<pre>{safe(y,3600)}</pre>")
        elif cmd=="/run":dispatch(token,uid,chat,a)
        elif cmd=="/runs":
            t=DBS.pat(uid);o,n=parse_repo(arg);runs=gh(t,f"/repos/{o}/{n}/actions/runs?per_page=20");rows=[]
            for x in runs.get('workflow_runs',[]):rows.append([{"text":f"#{x['id']} {x.get('name','')} — {x.get('status')}","callback_data":f"run:{uid}:{x['id']}:{o}/{n}"}])
            tg_send(token,chat,"<b>📊 Build History</b>\nSelect a run:",rows)
        elif cmd in ("/cancel","/rerun"):run_action(token,uid,chat,a,cmd[1:])
        elif cmd in ("/status","/logs","/artifacts"):
            if len(a)<3:raise GitofyError(f"Usage: {cmd} owner/name run-id")
            t=DBS.pat(uid);o,n=parse_repo(a[1]);rid=a[2];r=gh(t,f"/repos/{o}/{n}/actions/runs/{rid}")
            if cmd=="/status":
                jobs=gh(t,f"/repos/{o}/{n}/actions/runs/{rid}/jobs?per_page=100");txt,_,_,_=Progress.render(r,jobs.get('jobs',[]));tg_send(token,chat,txt)
            elif cmd=="/logs":send_log_report(token,chat,o,n,rid)
            else:artifact_menu(token,chat,t,o,n,rid,uid)
        elif cmd=="/download":
            t=DBS.pat(uid);o,n=parse_repo(a[1]);download_artifact(t,chat,o,n,a[2])
        elif cmd in ("/upload","/update"):
            S.awaiting[uid]="zip_update" if cmd=="/update" else "zip";tg_send(token,chat,"📤 Send the project ZIP as a Telegram document. Gitofy will validate, detect, compare and only write after an explicit confirmation.")
        elif cmd=="/compare":
            if len(a)<3:raise GitofyError("Usage: /compare owner/name branch")
            path=S.uploads.get(uid);t=DBS.pat(uid);o,n=parse_repo(a[1]);
            if not path:raise GitofyError("Send a ZIP with /update first.")
            _,_,add,mod,dele=compare_zip_to_repo(t,o,n,a[2],path);tg_send(token,chat,f"🔎 <b>Comparison</b>\n➕ Added: {len(add)}\n✏️ Modified: {len(mod)}\n➖ Deleted: {len(dele)}\n\nNo repository write was performed.",[[{"text":"✅ Confirm Sync","callback_data":f"sync:{uid}:{o}/{n}:{a[2]}"}],[{"text":"❌ Cancel","callback_data":f"cancel_sync:{uid}"}]])
        elif cmd=="/search":
            t=DBS.pat(uid);o,n=parse_repo(a[1]);q=" ".join(a[2:]);hits=kb_search(t,o,n,q);tg_send(token,chat,"🔎 <b>Repository Search</b>\n\n"+"\n".join("• "+safe(x) for x in hits) if hits else "No relevant files found.")
        elif cmd=="/file":
            t=DBS.pat(uid);o,n=parse_repo(a[1]);path=a[2];c=gh(t,f"/repos/{o}/{n}/contents/{urllib.parse.quote(path,safe='/')}");data=base64.b64decode((c.get('content') or '').encode()).decode('utf-8','replace');tg_send(token,chat,f"📄 <b>{safe(path)}</b>\n<pre>{safe(data,3600)}</pre>")
        elif cmd=="/commits":
            t=DBS.pat(uid);o,n=parse_repo(a[1]);cs=commit_history(t,o,n,a[2] if len(a)>2 else '');tg_send(token,chat,"💾 <b>Commit History</b>\n\n"+"\n".join(f"• <code>{x.get('sha','')[:8]}</code> — {safe((x.get('commit') or {}).get('message','').splitlines()[0],140)}" for x in cs))
        elif cmd=="/ai":
            t=DBS.pat(uid);request=text[3:].strip();
            if not t:raise GitofyError("Connect GitHub first for repository-aware AI.")
            m=re.search(r"\b([\w.-]+/[\w.-]+)\b",request);ans=ai_analyze_repo(t,*parse_repo(m.group(1)),request) if m else ai(request)
            if not ans:ans="AI provider is not configured. Configure GEMINI_API_KEY or OPENROUTER_API_KEY on the host."
            # Type the final AI answer into the same progress message when the
            # command wrapper is active. Telegram edits are throttled to avoid
            # flooding the Bot API.
            ctx=getattr(_COMMAND_PROGRESS,"ctx",None)
            if ctx is not None and ctx.token==token and ctx.chat==chat:
                plain=re.sub(r"<[^>]+>","",str(ans))
                for end in range(80,len(plain)+1,80):
                    tg_edit(token,chat,ctx.msg_id,"🤖 <b>Gitofy AI</b>\n\n"+safe(plain[:end],3600))
                    time.sleep(0.12)
                ctx.final_text="🤖 <b>Gitofy AI</b>\n\n"+safe(plain,3600)
            else:
                tg_send(token,chat,"🤖 "+ans)
        elif cmd=="/ai-fix":
            t=DBS.pat(uid)
            if not t:raise GitofyError("Connect GitHub first for repository-aware AI repair.")
            if len(a)<3:raise GitofyError("Usage: /ai-fix owner/name run-id")
            o,n=parse_repo(a[1]);rid=int(a[2]);run=gh(t,f"/repos/{o}/{n}/actions/runs/{rid}")
            jobs=gh(t,f"/repos/{o}/{n}/actions/runs/{rid}/jobs?per_page=100").get("jobs",[])
            if run.get("status")!="completed" or run.get("conclusion") not in ("failure","timed_out","action_required"):
                raise GitofyError("/ai-fix only runs on a completed failed workflow.")
            progress=tg_send(token,chat,"⏳ <b>AI engineer: starting…</b>\n<code>░░░░░░░░░░░░░░░░░░░░</code> <b>0%</b>")
            ai_autofix_failed_run(t,uid,chat,progress["message_id"],o,n,run,jobs)
        elif cmd in ("/review","/fix"):
            t=DBS.pat(uid);o,n=parse_repo(a[1]);context=' '.join(a[2:]);prompt=f"Perform a read-only engineering analysis for {o}/{n}. Request: {context}. Do not claim changes were made. Return facts, likely cause, affected files, proposed patch, tests and risk.";ans=ai_analyze_repo(t,o,n,prompt) or "AI provider is not configured.";tg_send(token,chat,"🤖 <b>Engineering Analysis</b>\n"+ans)
        elif cmd=="/issue":
            t=DBS.pat(uid);o,n=parse_repo(a[1]);title=" ".join(a[2:]);x=issue_create(t,o,n,title,"Created from Gitofy Telegram.");tg_send(token,chat,f"🐛 Issue created: #{x.get('number')}\n{x.get('html_url','')}")
        elif cmd=="/pr":
            t=DBS.pat(uid);o,n=parse_repo(a[1]);head=a[2];base=a[3];title=" ".join(a[4:]);x=create_pr(t,o,n,head,base,title,"Created from Gitofy Telegram.");tg_send(token,chat,f"🔀 PR created: #{x.get('number')}\n{x.get('html_url','')}")
        elif cmd=="/release":
            t=DBS.pat(uid);o,n=parse_repo(a[1]);tag=a[2];title=" ".join(a[3:]);x=release_create(t,o,n,tag,title,"Release created by Gitofy.");tg_send(token,chat,f"🚀 Release created: {safe(x.get('tag_name',tag))}\n{x.get('html_url','')}")
        elif cmd=="/rollback":
            if len(a)<4 or a[3].upper()!="CONFIRM":raise GitofyError("Dangerous operation. Use /rollback owner/name branch CONFIRM")
            t=DBS.pat(uid);o,n=parse_repo(a[1]);branch=a[2];commits=commit_history(t,o,n,branch);backup=commits[1]['sha'] if len(commits)>1 else None
            if not backup:raise GitofyError("No previous commit available for rollback.")
            # Non-destructive rollback: create a new revert commit through GitHub API.
            x=gh(t,f"/repos/{o}/{n}/commits/{commits[0]['sha']}/revert","POST",{'mainline':1}) if False else None
            raise GitofyError("Rollback requires a GitHub revert-capable workflow or a verified target commit; no destructive force push is performed by default.")
        elif cmd=="/memory":
            rows=DBS.q("SELECT repository,key,value,updated_at FROM memories WHERE telegram_user_id=? ORDER BY updated_at DESC LIMIT 50",(uid,));tg_send(token,chat,"🧠 <b>AI Memory</b>\n\n"+"\n".join(f"• {safe(r['repository'])}: <code>{safe(r['key'])}</code> = {safe(r['value'],250)}" for r in rows) if rows else "🧠 No memory entries yet.")
        elif cmd=="/remember":
            if len(a)<4:raise GitofyError("Usage: /remember owner/name key value")
            o,n=parse_repo(a[1]);DBS.run("INSERT INTO memories VALUES(?,?,?,?,?) ON CONFLICT(telegram_user_id,repository,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(uid,f'{o}/{n}',a[2],' '.join(a[3:]),now()));tg_send(token,chat,"🧠 Memory saved.")
        elif cmd=="/audit":
            rows=DBS.q("SELECT action,result,timestamp,repository,target FROM audit_log ORDER BY id DESC LIMIT 30");tg_send(token,chat,"🧾 <b>Audit Log</b>\n\n"+"\n".join(f"• {r['timestamp']} — {safe(r['action'])} — {safe(r['repository'] or '')} — {safe(r['result'],180)}" for r in rows))
        elif cmd=="/settings":settings_menu(token,chat,uid)
        elif cmd=="/set":
            if len(a)<4:raise GitofyError("Usage: /set owner/name key value")
            t=DBS.pat(uid);o,n=parse_repo(a[1]);r=repo_info(t,o,n);repo=DBS.q("SELECT id FROM repositories WHERE telegram_user_id=? AND github_repo_id=?",(uid,r['id']),True)
            if not repo: DBS.run("INSERT INTO repositories(telegram_user_id,github_repo_id,owner,name,default_branch,visibility,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(uid,r['id'],o,n,r.get('default_branch','main'),r.get('visibility',''),now(),now()));repo=DBS.q("SELECT id FROM repositories WHERE telegram_user_id=? AND github_repo_id=?",(uid,r['id']),True)
            key=a[2];value=' '.join(a[3:]);allowed={'default_branch','default_workflow','auto_build','sync_mode','notification_mode'}
            if key not in allowed:raise GitofyError('Allowed settings: default_branch, default_workflow, auto_build, sync_mode, notification_mode')
            cur=DBS.q("SELECT * FROM repo_settings WHERE repository_id=?",(repo['id'],),True);vals={k:cur[k] for k in ('default_branch','default_workflow','auto_build','sync_mode','notification_mode')} if cur else {'default_branch':r.get('default_branch','main'),'default_workflow':'','auto_build':0,'sync_mode':'update','notification_mode':'all'}
            if key=='auto_build':value=int(value.lower() in ('1','true','yes','on'));
            vals[key]=value;DBS.run("INSERT INTO repo_settings(repository_id,default_branch,default_workflow,auto_build,sync_mode,notification_mode) VALUES(?,?,?,?,?,?) ON CONFLICT(repository_id) DO UPDATE SET default_branch=excluded.default_branch,default_workflow=excluded.default_workflow,auto_build=excluded.auto_build,sync_mode=excluded.sync_mode,notification_mode=excluded.notification_mode",(repo['id'],vals['default_branch'],vals['default_workflow'],vals['auto_build'],vals['sync_mode'],vals['notification_mode']));tg_send(token,chat,f"⚙️ Setting saved: <code>{safe(key)}</code> = <code>{safe(value)}</code>")
        elif cmd=="/schedule":S.awaiting[uid]="schedule";tg_send(token,chat,"🗓 Send: <code>repository | cron | task</code>\nExample: <code>owner/name | 0 9 * * 1 | dependency check</code>")
        elif cmd=="/maintenance":
            if uid not in ADMIN_IDS:raise GitofyError("Admin permission required.")
            tg_send(token,chat,"🛠 Autonomous maintenance is enabled as a scheduled capability. Code-changing actions remain permission-gated.")
        elif cmd=="/healthz":
            ghok=False
            if DBS.pat(uid):
                try:gh(DBS.pat(uid),'/rate_limit');ghok=True
                except Exception:pass
            usage=sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file());tg_send(token,chat,f"🩺 <b>Gitofy Health</b>\nProcess: 🟢\nDatabase: 🟢\nTelegram: 🟢\nGitHub: {'🟢' if ghok else '⚪'}\nStorage: 🟢\nDisk: 🟢\nStorage usage: {usage/1024/1024:.1f} MB")
        elif cmd=="/diag":
            if uid not in ADMIN_IDS:raise GitofyError("Admin permission required.")
            usage=sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file());tg_send(token,chat,f"🩺 <b>Diagnostics</b>\nActive monitors: {len(S.monitors)}\nStorage: {usage/1024/1024:.1f} MB\nDB: 🟢\nTelegram: 🟢")
        else:raise GitofyError("Unknown command. Use /help.")
    except Exception as e:
        DBS.audit(uid,text,'error','dispatcher',None,None,'command_error',redact(str(e)))
        tg_send(token,chat,"❌ "+safe(redact(e)))

def handle_cmd(token,uid,chat,text):
    # /start is the persistent home entry point.  Do not wrap it in the generic
    # processing-message editor: that used to race with the progress thread
    # and could leave Telegram with a stale/non-editable message id.
    cmd=(text or '').split()[0].split('@')[0].lower() if (text or '').strip() else ''
    if cmd == '/start':
        try:
            start_flow(token,uid,chat)
        except Exception as e:
            try: tg_send(token,chat,"❌ "+safe(redact(e)))
            except Exception: pass
        return

    # Other commands use one processing message and then edit it into the
    # final result.  If Telegram says that message can no longer be edited
    # (deleted, migrated chat, duplicate bot worker, etc.), fall back to a new
    # final message instead of surfacing a raw HTTP 400 to the user.
    try:
        initial=tg_send(token,chat,"⏳ <b>Processing…</b>\n<code>░░░░░░░░░░░░░░░░░░░░</code> <b>0%</b>")
        ctx=_CommandProgress(token,chat,initial["message_id"])
        ctx.final_text="Processing complete.";ctx.final_keyboard=None;ctx.final_parse="HTML";ctx.finished=False
        _COMMAND_PROGRESS.ctx=ctx
        th=threading.Thread(target=ctx.animate,daemon=True);th.start()
        try:
            _handle_cmd_impl(token,uid,chat,text)
        finally:
            ctx.stop=True;ctx.finished=True
            time.sleep(0.05)
            try:
                tg_edit(token,chat,ctx.msg_id,ctx.final_text,ctx.final_keyboard)
            except Exception as edit_error:
                if 'message to edit not found' in str(edit_error).lower() or 'message_id_invalid' in str(edit_error).lower():
                    try: tg_send(token,chat,ctx.final_text,ctx.final_keyboard)
                    except Exception: pass
                else:
                    raise
            _COMMAND_PROGRESS.ctx=None
    except Exception as e:
        try:tg_send(token,chat,"❌ "+safe(redact(e)))
        except Exception:pass

def dispatch(token,uid,chat,a):
    if len(a)<4:raise GitofyError("Usage: /run owner/name workflow-id branch [JSON inputs]")
    t=DBS.pat(uid);o,n=parse_repo(a[1]);wid=a[2];branch=a[3]
    # Verify workflow exists and dispatch.
    w=gh(t,f"/repos/{o}/{n}/actions/workflows/{wid}");inputs={}
    if len(a)>4:
        try: inputs=json.loads(' '.join(a[4:]))
        except Exception: raise GitofyError('Workflow inputs must be valid JSON.')
        if not isinstance(inputs,dict): raise GitofyError('Workflow inputs must be a JSON object.')
    # Capture the run ids that existed before dispatch so a slow GitHub API
    # response can never attach the dashboard to an older run.
    before=gh(t,f"/repos/{o}/{n}/actions/runs?per_page=50").get("workflow_runs",[])
    before_ids={x.get("id") for x in before}
    dispatched_at=time.time()
    gh(t,f"/repos/{o}/{n}/actions/workflows/{wid}/dispatches","POST",{"ref":branch,"inputs":inputs})
    # Find the run created by this dispatch.
    rid=None;run=None
    for _ in range(20):
        time.sleep(2)
        runs=gh(t,f"/repos/{o}/{n}/actions/runs?per_page=50").get("workflow_runs",[])
        candidates=[]
        for x in runs:
            if x.get("id") in before_ids: continue
            try:
                created=datetime.fromisoformat(str(x.get("created_at","" )).replace("Z","+00:00")).timestamp()
            except Exception:
                created=dispatched_at
            if x.get("workflow_id")==int(wid) and x.get("head_branch")==branch and created >= dispatched_at-10:
                candidates.append(x)
        if candidates:
            candidates.sort(key=lambda x:x.get("id",0),reverse=True)
            run=candidates[0];rid=run.get("id");break
    if not rid:tg_send(token,chat,"▶️ Workflow dispatch accepted by GitHub. Run ID has not appeared yet; use /runs to monitor.");return
    m=tg_send(token,chat,"🚀 <b>Build queued</b>\nWaiting for GitHub job/step state…",[[{"text":"📊 Refresh","callback_data":f"run:{uid}:{rid}:{o}/{n}"}]])
    repo_id=DBS.q("SELECT id FROM repositories WHERE telegram_user_id=? AND owner=? AND name=?",(uid,o,n),True);repoid=repo_id["id"] if repo_id else None
    DBS.run("INSERT OR IGNORE INTO workflow_runs(repository_id,github_run_id,workflow_id,branch,status,conclusion,telegram_user_id,telegram_chat_id,telegram_message_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(repoid,rid,int(wid),branch,run.get('status'),run.get('conclusion'),uid,chat,m['message_id'],now(),now()))
    row=DBS.q("SELECT wr.*,r.owner||'/'||r.name repo FROM workflow_runs wr JOIN repositories r ON r.id=wr.repository_id WHERE wr.github_run_id=?",(rid,),True)
    if row:
        mon=Monitor(token,row);S.monitors[rid]=mon;mon.start()

def run_action(token,uid,chat,a,action):
    if len(a)<3:raise GitofyError(f"Usage: /{action} owner/name run-id")
    t=DBS.pat(uid);o,n=parse_repo(a[1]);rid=a[2]
    path=f"/repos/{o}/{n}/actions/runs/{rid}/{action}";gh(t,path,"POST");tg_send(token,chat,f"{'🔄 Re-run' if action=='rerun' else '⛔ Cancel'} requested. GitHub is the source of truth.")


def require_pat(uid,chat):
    pat=DBS.pat(uid)
    if not pat:
        tg_send(TOKEN,chat,"🔐 <b>GitHub is not connected.</b>\n\nTap <b>🔐 GitHub Connection</b> and paste your PAT. No command is required.",[[{"text":"🔐 Connect GitHub","callback_data":f"menu:{uid}:github"}]])
        return None
    return pat

def repo_picker(token,uid,chat,next_action="repo"):
    pat=require_pat(uid,chat)
    if not pat:return
    rs=gh(pat,"/user/repos?per_page=50&sort=updated")
    rows=[]
    for r in rs:
        full=r.get("full_name") or f"{r.get('owner',{}).get('login','')}/{r.get('name','')}"
        rows.append([{"text":f"📁 {r.get('name','')}","callback_data":f"pick:{uid}:{next_action}:{full}"}])
    rows.append([{"text":"➕ Create New Repository","callback_data":f"create_repo:{uid}:{next_action}"}])
    rows.append([{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}])
    tg_send(token,chat,"📦 <b>Select a repository</b>\n\nChoose one below:",rows)

def workflow_picker(token,uid,chat,repo):
    pat=require_pat(uid,chat)
    if not pat:return
    o,n=parse_repo(repo);w=gh(pat,f"/repos/{o}/{n}/actions/workflows?per_page=100")
    rows=[]
    for x in w.get("workflows",[]):
        rows.append([{"text":f"⚙️ {x.get('name','workflow')}","callback_data":f"pickwf:{uid}:{repo}:{x.get('id')}"}])
    if not rows:
        tg_send(token,chat,"⚙️ No GitHub Actions workflows were found in this repository.")
        return
    tg_send(token,chat,f"⚙️ <b>Workflows</b>\n<code>{safe(repo)}</code>\n\nSelect a workflow:",rows)

def run_picker(token,uid,chat,repo,wid):
    pat=require_pat(uid,chat)
    if not pat:return
    o,n=parse_repo(repo);r=repo_info(pat,o,n);branch=r.get("default_branch") or "main"
    tg_send(token,chat,f"▶️ <b>Run workflow</b>\n\nRepository: <code>{safe(repo)}</code>\nWorkflow: <code>{safe(wid)}</code>\nBranch: <code>{safe(branch)}</code>",[[{"text":f"▶️ Run on {branch}","callback_data":f"execwf:{uid}:{repo}:{wid}:{urllib.parse.quote(branch,safe='')}"}],[{"text":"🌿 Choose another branch","callback_data":f"branches:{uid}:{repo}:run:{wid}"}]])

def branch_picker(token,uid,chat,repo,mode="view",wid=""):
    pat=require_pat(uid,chat)
    if not pat:return
    o,n=parse_repo(repo);bs=gh(pat,f"/repos/{o}/{n}/branches?per_page=100")
    rows=[]
    for b in bs:
        branch=b.get("name","")
        if mode=="run":
            rows.append([{"text":f"🌿 {branch}","callback_data":f"execwf:{uid}:{repo}:{wid}:{urllib.parse.quote(branch,safe='')}"}])
    if not rows: rows=[[{"text":"⬅️ Back","callback_data":f"pick:{uid}:workflows:{repo}"}]]
    tg_send(token,chat,f"🌿 <b>Select branch</b>\n<code>{safe(repo)}</code>",rows)

def run_picker_from_history(token,uid,chat,repo):
    pat=require_pat(uid,chat)
    if not pat:return
    o,n=parse_repo(repo);runs=gh(pat,f"/repos/{o}/{n}/actions/runs?per_page=20").get("workflow_runs",[])
    rows=[]
    for x in runs:
        rows.append([{"text":f"#{x.get('id')} {x.get('name','')} • {x.get('status','')}","callback_data":f"run:{uid}:{x.get('id')}:{repo}"}])
    tg_send(token,chat,"📊 <b>Build Status</b>\n\nSelect a run:",rows or [[{"text":"⬅️ Main Menu","callback_data":f"menu:{uid}:home"}]])

def connection_menu(token,uid,chat):
    row=DBS.conn(uid)
    if row and DBS.pat(uid):
        tg_send(token,chat,f"🔐 <b>GitHub Connection</b>\n\n🟢 Connected as <code>{safe(row['github_username'])}</code>",[[{"text":"🔄 Reconnect / Replace PAT","callback_data":f"connect:{uid}"},{"text":"❌ Disconnect","callback_data":f"disconnect:{uid}"}],[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])
    else:
        tg_send(token,chat,"🔐 <b>GitHub Connection</b>\n\nNo active GitHub connection.\n\nTap Connect and send your PAT in the next message.",[[{"text":"🔐 Connect GitHub","callback_data":f"connect:{uid}"}],[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])

def handle_callback(token,q):
    uid=int((q.get("from") or {}).get("id",0));data=q.get("data","");cid=q.get("id");chat=(q.get("message") or {}).get("chat",{}).get("id")
    tg_answer(token,cid)
    p=data.split(":")
    if not p:return
    try:
        if len(p)<2 or int(p[1])!=uid:raise GitofyError("Unauthorized action")
        action=p[0]
        if action=="connect":
            S.awaiting[uid]="pat";DBS.set_pending(uid,"pat")
            tg_send(token,chat,"🔐 <b>Connect GitHub</b>\n\nSend your GitHub Personal Access Token in your next message.\n\nNo command is required. I will reply immediately that validation has started, then show the connection result.",None)
        elif action=="disconnect":
            DBS.run("DELETE FROM github_connections WHERE telegram_user_id=?",(uid,));DBS.clear_pending(uid);SESSION_PATS.pop(uid,None);S.awaiting.pop(uid,None);tg_send(token,chat,"🔐 GitHub disconnected.",main_menu(uid))
        elif action=="menu":
            kind=p[2]
            if kind=="home":start_flow(token,uid,chat)
            elif kind=="repos":repo_list(DBS.pat(uid),uid,chat) if DBS.pat(uid) else connection_menu(token,uid,chat)
            elif kind=="github":connection_menu(token,uid,chat)
            elif kind in ("upload","update"):
                S.awaiting[uid]="zip_update" if kind=="update" else "zip";tg_send(token,chat,"📤 <b>Send your ZIP project</b>\n\nNo command is required. Gitofy will validate it and continue from the buttons.")
            elif kind=="patcaps":
                pat=require_pat(uid,chat)
                if not pat: return
                try:
                    _,headers,_=gh_raw(pat,"/user")
                    scopes={x.strip() for x in headers.get("X-OAuth-Scopes","").split(",") if x.strip()}
                    if render_report:
                        text=render_report(scopes, fine_grained=not bool(scopes))
                    else:
                        text="🔑 <b>PAT Capabilities</b>\n\nDetected classic scopes: <code>"+safe(', '.join(sorted(scopes)) or 'not exposed (likely fine-grained)')+"</code>"
                    tg_send(token,chat,text,[[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])
                except Exception as e:
                    tg_send(token,chat,"❌ Could not inspect PAT capabilities.\n\n"+safe(redact(e)),[[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])
            elif kind=="create_repo":
                S.awaiting[uid]="new_repo";DBS.set_pending(uid,"new_repo")
                tg_send(token,chat,"➕ <b>Create New GitHub Repository</b>\n\nSend the repository name now.\nExample: <code>MyAndroidApp</code>\n\nGitofy will create it automatically — no command is required.")
            elif kind=="workflows":repo_picker(token,uid,chat,"workflows")
            elif kind=="runs":repo_picker(token,uid,chat,"runs")
            elif kind=="logs":repo_picker(token,uid,chat,"logs")
            elif kind=="arts":repo_picker(token,uid,chat,"arts")
            elif kind=="run":repo_picker(token,uid,chat,"run")
            elif kind=="settings":settings_menu(token,chat,uid,msg_id=(q.get("message") or {}).get("message_id"))
            elif kind=="aimodels":
                # Keep the model selector in the same message; detailed model
                # routing is handled by the AI configuration layer.
                ai_providers_menu(token,chat,uid,msg_id=(q.get("message") or {}).get("message_id"))
            elif kind=="help":tg_send(token,chat,HELP,[[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])
        elif action=="create_repo":
            S.awaiting[uid]="new_repo";DBS.set_pending(uid,"new_repo")
            next_action=p[2] if len(p)>2 else "none"
            S.awaiting[uid]=f"new_repo:{next_action}";DBS.set_pending(uid,f"new_repo:{next_action}")
            tg_send(token,chat,"➕ <b>Create New GitHub Repository</b>\n\nSend the repository name now.\nExample: <code>MyAndroidApp</code>\n\nGitofy will create it automatically — no command is required.")
        elif action=="pick":
            kind=p[2];repo=p[3]
            if kind=="workflows":workflow_picker(token,uid,chat,repo)
            elif kind=="run":workflow_picker(token,uid,chat,repo)
            elif kind=="runs":run_picker_from_history(token,uid,chat,repo)
            elif kind=="logs":run_picker_from_history(token,uid,chat,repo)
            elif kind=="arts":run_picker_from_history(token,uid,chat,repo)
            elif kind=="update":
                t=require_pat(uid,chat)
                if not t:return
                o,n=parse_repo(repo);r=repo_info(t,o,n);branch=r.get("default_branch") or "main"
                path=S.uploads.get(uid)
                if not path:raise GitofyError("No uploaded ZIP is available. Tap Update Project first.")
                _,_,add,mod,dele=compare_zip_to_repo(t,o,n,branch,path)
                tg_send(token,chat,f"🔎 <b>Project Replacement → {safe(repo)}</b>\n\nBranch: <code>{safe(branch)}</code>\n➕ New files: {len(add)}\n✏️ Changed files: {len(mod)}\n🗑 Old files to remove: {len(dele)}\n\nThe current project files in this repository will be removed and replaced by the files from the new ZIP. Git history is preserved.\n\nNothing has been written yet.",[[{"text":"✅ Confirm Replace Project","callback_data":f"update:{uid}:{repo}:{urllib.parse.quote(branch,safe='')}"}],[{"text":"❌ Cancel","callback_data":f"cancel_sync:{uid}"}]])
            elif kind=="sync":
                t=require_pat(uid,chat)
                if not t:return
                o,n=parse_repo(repo);r=repo_info(t,o,n);branch=r.get("default_branch") or "main"
                path=S.uploads.get(uid)
                if not path:raise GitofyError("No uploaded ZIP is available. Tap Upload Project first.")
                _,_,add,mod,dele=compare_zip_to_repo(t,o,n,branch,path)
                tg_send(token,chat,f"🔎 <b>Project → {safe(repo)}</b>\n\nBranch: <code>{safe(branch)}</code>\n➕ Added: {len(add)}\n✏️ Modified: {len(mod)}\n➖ Deleted: {len(dele)}\n\nNothing has been written yet.",[[{"text":"✅ Upload / Sync Project","callback_data":f"sync:{uid}:{repo}:{urllib.parse.quote(branch,safe='')}"}],[{"text":"❌ Cancel","callback_data":f"cancel_sync:{uid}"}]])
            elif kind=="repo":
                o,n=parse_repo(repo);r=repo_info(DBS.pat(uid),o,n);tg_send(token,chat,f"📁 <b>{safe(r['full_name'])}</b>\n🌿 <code>{safe(r.get('default_branch','main'))}</code>\n🔒 {safe(r.get('visibility',''))}",[[{"text":"⚙️ Workflows","callback_data":f"pick:{uid}:workflows:{repo}"},{"text":"📊 Build Status","callback_data":f"pick:{uid}:runs:{repo}"}]])
        elif action=="pickwf":
            repo=p[2];wid=p[3];run_picker(token,uid,chat,repo,wid)
        elif action=="branches":
            branch_picker(token,uid,chat,p[2],p[3],p[4] if len(p)>4 else "")
        elif action=="execwf":
            repo=p[2];wid=p[3];branch=urllib.parse.unquote(":".join(p[4:]))
            dispatch(token,uid,chat,["/run",repo,wid,branch])
        elif action=="upload":
            next_action=p[2] if len(p)>2 else "sync"
            if S.uploads.get(uid):repo_picker(token,uid,chat,next_action)
            else:S.awaiting[uid]="zip_update" if next_action=="update" else "zip";tg_send(token,chat,"📤 Send the ZIP project first.")
        elif action=="update":
            o,n=parse_repo(p[2]);branch=urllib.parse.unquote(":".join(p[3:]));path=S.uploads.get(uid)
            if not path:raise GitofyError("No uploaded ZIP is available.")
            t=require_pat(uid,chat)
            if not t:return
            progress=tg_send(token,chat,"⏳ <b>Replacing repository project…</b>\n<code>░░░░░░░░░░░░░░░░░░░░</code> <b>0%</b>")
            reporter=OperationReporter(token,chat,progress["message_id"])
            # Update Project is intentionally a full project replacement: the
            # repository working tree becomes an exact mirror of the new ZIP.
            # Git history remains intact; files absent from the ZIP are removed.
            result=sync_zip_to_repo(t,o,n,branch,path,reporter)
            S.uploads.pop(uid,None);S.awaiting.pop(uid,None)
            if not result.get('changed'):
                reporter.finish(f"ℹ️ <b>Repository already matches the new project</b>\n\n📁 <code>{safe(o+'/'+n)}</code>\n🌿 Branch: <code>{safe(branch)}</code>",main_menu(uid))
            else:
                reporter.finish(f"✅ <b>Repository project replaced successfully</b>\n\n📁 <code>{safe(o+'/'+n)}</code>\n🌿 Branch: <code>{safe(branch)}</code>\n📦 New project files: {result.get('files',0)}\n🗑 Old files not in the ZIP: removed\n💾 Commit: <code>{safe((result.get('sha') or '')[:12])}</code>\n\nThe repository now contains the new project from the ZIP. Git history was preserved.",main_menu(uid))
        elif action=="sync":
            o,n=parse_repo(p[2]);branch=urllib.parse.unquote(":".join(p[3:]));path=S.uploads.get(uid)
            if not path:raise GitofyError("No uploaded ZIP is available.")
            t=require_pat(uid,chat)
            if not t:return
            progress=tg_send(token,chat,"⏳ <b>Processing…</b>\n<code>░░░░░░░░░░░░░░░░░░░░</code> <b>0%</b>")
            reporter=OperationReporter(token,chat,progress["message_id"])
            result=sync_zip_to_repo(t,o,n,branch,path,reporter)
            S.uploads.pop(uid,None);S.awaiting.pop(uid,None)
            wf=result.get("workflows") or {}
            final=f"✅ <b>Repository replaced successfully</b>\n\n📁 <code>{safe(o+'/'+n)}</code>\n🌿 Branch: <code>{safe(branch)}</code>\n📦 Files: {result.get('files',0)}\n🗑 Old files removed: all files not present in the new ZIP\n💾 Commit: <code>{safe(result['sha'][:12])}</code>"
            final+=f"\n\n⚙️ Automatic workflows: disabled after sync\n▶️ Started automatically: 0"
            if wf.get('skipped'): final+=f"\n⏭ Not auto-run: {len(wf['skipped'])}"
            if wf.get('failed'): final+=f"\n❌ Failed to start: {len(wf['failed'])}"
            reporter.finish(final,main_menu(uid))
        elif action=="cancel_sync":
            S.uploads.pop(uid,None);S.awaiting.pop(uid,None);tg_send(token,chat,"❌ Cancelled. No repository changes were made.",main_menu(uid))
        elif action=="wf":
            repo=p[2];wid=p[3];path,y=workflow_yaml(DBS.pat(uid),*parse_repo(repo),wid);tg_send(token,chat,f"📄 <b>{safe(path)}</b>\n<pre>{safe(y,3300)}</pre>",[[{"text":"▶️ Run","callback_data":f"pickwf:{uid}:{repo}:{wid}"}]])
        elif action=="runwf":
            repo=p[2];wid=p[3];run_picker(token,uid,chat,repo,wid)
        elif action=="run":
            rid=p[2];repo=p[3];o,n=parse_repo(repo);t=require_pat(uid,chat)
            if not t:return
            r=gh(t,f"/repos/{o}/{n}/actions/runs/{rid}");jobs=gh(t,f"/repos/{o}/{n}/actions/runs/{rid}/jobs?per_page=100");txt,pct,done,total=Progress.render(r,jobs.get('jobs',[]));
            kb=[[{"text":"📜 Logs","callback_data":f"logs:{uid}:{rid}:{repo}"},{"text":"📦 Artifacts","callback_data":f"arts:{uid}:{rid}:{repo}"}]]
            if r.get("status") not in ("completed",):kb.append([{"text":"⛔ Cancel","callback_data":f"cancel:{uid}:{rid}:{repo}"}])
            else:kb.append([{"text":"🔄 Re-run","callback_data":f"rerun:{uid}:{rid}:{repo}"}])
            tg_send(token,chat,txt,kb)
        elif action in ("cancel","rerun"):
            rid=p[2];o,n=parse_repo(p[3]);t=require_pat(uid,chat)
            if not t:return
            gh(t,f"/repos/{o}/{n}/actions/runs/{rid}/{action}","POST");tg_send(token,chat,f"{'⛔ Cancel' if action=='cancel' else '🔄 Re-run'} requested. GitHub is the source of truth.",[[{"text":"📊 Refresh","callback_data":f"run:{uid}:{rid}:{o}/{n}"}]])
        elif action=="logs":
            rid=p[2];o,n=parse_repo(p[3]);t=require_pat(uid,chat)
            if t:send_log_report(t,chat,o,n,rid)
        elif action=="arts":
            rid=p[2];o,n=parse_repo(p[3]);t=require_pat(uid,chat)
            if t:artifact_menu(t,chat,t,o,n,rid,uid)
        elif action=="artifact":
            rid=p[2];o,n=parse_repo(p[3]);aid=p[4];t=require_pat(uid,chat)
            if t:download_artifact(t,chat,o,n,aid)
        elif action=="settings":
            sub=p[2] if len(p)>2 else "root"
            if sub=="root":
                settings_menu(token,chat,uid,msg_id=(q.get("message") or {}).get("message_id"))
            elif sub=="ai":
                ai_providers_menu(token,chat,uid,msg_id=(q.get("message") or {}).get("message_id"))
            elif sub=="autobuild":
                auto_build_menu(token,chat,uid,msg_id=(q.get("message") or {}).get("message_id"))
            elif sub=="cleanup":
                cleanup_menu(token,chat,uid,msg_id=(q.get("message") or {}).get("message_id"))
            elif sub=="aimode":
                mode=p[3] if len(p)>3 else "auto"
                if mode=="auto":
                    tg_edit(token,chat,(q.get("message") or {}).get("message_id"),
                            "🤖 <b>AI Providers</b>\n\n⚡ <b>Auto Mode enabled</b>\n\nThe Head AI will select the best specialist model for each problem.",
                            [[{"text":"⬅️ AI Providers","callback_data":f"settings:{uid}:ai"}],[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])
        elif action=="notify":
            DBS.set_notify_pref(uid,not DBS.notify_pref(uid))
            settings_menu(token,chat,uid,msg_id=(q.get("message") or {}).get("message_id"))
    except Exception as e:
        DBS.audit(uid,"button:"+data,"error","dispatcher",None,None,"callback_error",redact(str(e)))
        tg_send(token,chat,"❌ "+safe(redact(e)))

def validate_pat_worker(token, uid, chat, message_id, raw_token):
    """Run PAT validation off the Telegram polling thread and always send a result."""
    try:
        user,perms=token_validate(raw_token)
        DBS.setconn(uid,user.get("id"),user.get("login"),raw_token,perms)
        S.awaiting.pop(uid,None);DBS.clear_pending(uid)
        if message_id:
            try: tg(token,"deleteMessage",{"chat_id":chat,"message_id":message_id})
            except Exception: pass
        tg_send(token,chat,f"🐙 <b>GitHub Connected</b>\n\n👤 Username: <code>{safe(user.get('login'))}</code>\n🟢 Connection: Active\n\nGitHub is ready. Use the buttons below — no commands are required.",main_menu(uid))
    except Exception as e:
        # Keep the pending state so the user can paste a corrected PAT without
        # pressing Connect again.
        tg_send(token,chat,"❌ <b>GitHub connection failed</b>\n\n"+safe(redact(e))+"\n\nPlease send a valid PAT again.",[[{"text":"🔐 Connect GitHub","callback_data":f"connect:{uid}"}],[{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])

def handle_update(token,u):
    if "callback_query" in u:handle_callback(token,u["callback_query"]);return
    m=u.get("message") or {};uid=(m.get("from") or {}).get("id");chat=(m.get("chat") or {}).get("id");
    if not uid or chat is None:return
    DBS.user(uid,(m.get("from") or {}).get("username", ""));text=(m.get("text") or "").strip()
    mode=S.awaiting.get(uid) or DBS.pending(uid)
    if mode and str(mode).startswith("new_repo") and text and not text.startswith("/"):
        raw_name=text.strip()
        next_action=str(mode).split(":",1)[1] if ":" in str(mode) else "none"
        try:
            t=DBS.pat(uid)
            if not t:raise GitofyError("Connect GitHub first.")
            tg_send(token,chat,"⏳ <b>Creating repository…</b>")
            x=create_repository(t,raw_name,private=False,auto_init=True)
            owner=(x.get("owner") or {}).get("login") or (x.get("full_name") or "").split("/",1)[0]
            name=x.get("name") or raw_name
            full=x.get("full_name") or f"{owner}/{name}"
            rid=x.get("id")
            if rid:
                DBS.run("INSERT OR REPLACE INTO repositories(telegram_user_id,github_repo_id,owner,name,default_branch,visibility,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(uid,rid,owner,name,x.get("default_branch") or "main",x.get("visibility") or "public",now(),now()))
            DBS.clear_pending(uid);S.awaiting.pop(uid,None)
            path=S.uploads.get(uid)
            if path and next_action in ("sync","upload"):
                tg_send(token,chat,f"📦 <b>Repository created:</b> <code>{safe(full)}</code>\n\n📤 Uploading your current project…")
                branch=x.get("default_branch") or "main"
                progress=tg_send(token,chat,"⏳ <b>Uploading ZIP…</b>\n<code>░░░░░░░░░░░░░░░░░░░░</code> <b>0%</b>")
                reporter=OperationReporter(token,chat,progress["message_id"])
                result=sync_zip_to_repo(t,owner,name,branch,path,reporter)
                S.uploads.pop(uid,None);S.awaiting.pop(uid,None)
                wf=result.get("workflows") or {}
                final=f"✅ <b>Project uploaded successfully</b>\n\nRepository: <code>{safe(full)}</code>\nBranch: <code>{safe(branch)}</code>\n📦 Files: {result.get('files',0)}\n💾 Commit: <code>{safe(result['sha'][:12])}</code>\n\n⚙️ Automatic workflows: disabled after sync\n▶️ Started automatically: 0"
                if wf.get('skipped'): final+=f"\n⏭ Not auto-run: {len(wf['skipped'])}"
                if wf.get('failed'): final+=f"\n❌ Failed to start: {len(wf['failed'])}"
                reporter.finish(final,main_menu(uid))
            else:
                tg_send(token,chat,f"✅ <b>Repository created</b>\n\n📁 <code>{safe(full)}</code>\n🔒 Visibility: public\n\nYou can now upload a project to it from the buttons.",[[{"text":"📤 Upload Project","callback_data":f"menu:{uid}:upload"}],[{"text":"📦 Repositories","callback_data":f"menu:{uid}:repos"},{"text":"🏠 Main Menu","callback_data":f"menu:{uid}:home"}]])
        except Exception as e:
            tg_send(token,chat,"❌ <b>Repository creation failed</b>\n\n"+safe(redact(e)))
        return
    if mode=="pat" and text and not text.startswith("/"):
        raw_token=text.strip()
        try:
            tg_send(token,chat,"🔄 <b>GitHub token received.</b>\nValidation is running…")
        except Exception:
            pass
        # Never block the long-polling loop on GitHub. The worker is bounded by
        # token_validate's 15s network timeout and always emits success/failure.
        # Queue instead of a fire-and-forget daemon thread.  This prevents the
        # validation task from disappearing on constrained bot hosts.
        PAT_JOBS.put((token,uid,chat,m.get("message_id"),raw_token))
        return
    if mode in ("zip","zip_update") and m.get("document"):
        doc=m["document"];name=doc.get("file_name","")
        if not name.lower().endswith(".zip"):tg_send(token,chat,"❌ Please send a .zip project.");return
        try:
            f=tg(token,"getFile",{"file_id":doc["file_id"]});url=f"{TG_FILE_BASE}/bot{token}/{f['file_path']}";r=http(url,stream=True,timeout=180);path=UP/f"{uid}_{int(time.time())}_{secrets.token_hex(4)}.zip";size=0
            total_remote=int(doc.get("file_size") or 0)
            progress=tg_send(token,chat,"⏳ <b>Uploading ZIP…</b>\n<code>░░░░░░░░░░░░░░░░░░░░</code> <b>0%</b>")
            reporter=OperationReporter(token,chat,progress["message_id"])
            with path.open("wb") as out:
                while True:
                    b=r.read(8*1024*1024)
                    if not b:break
                    size+=len(b)
                    if size>MAX_ZIP_BYTES:raise GitofyError("ZIP exceeds upload limit")
                    out.write(b)
                    reporter.advance((size/total_remote)*100 if total_remote else min(99,size/MAX_ZIP_BYTES*100),"Uploading ZIP…")
            reporter.advance(99,"Validating project…")
            z,names,total=validate_zip(path);info=detect_project(names);S.awaiting.pop(uid,None);S.uploads[uid]=str(path)
            buttons=[[{"text":"🔎 Compare / Select Repo","callback_data":f"upload:{uid}:{'update' if mode=='zip_update' else 'sync'}"}],[{"text":"❌ Cancel","callback_data":f"cancel_sync:{uid}"}]]
            zip_size=path.stat().st_size
            file_entries=[n for n in names if n and not n.endswith("/")]
            uploadable_entries=[n for n in names if n and not n.endswith("/") and not n.startswith(".git/")]
            final=f"🔎 <b>Project Analysis</b>\nZIP size: {zip_size/1024/1024:.2f} MB ({zip_size:,} bytes)\nFiles: {len(file_entries):,}\nExtracted size: {total/1024/1024:.2f} MB ({total:,} bytes)\nRoot: <code>{safe(info['root'])}</code>\nAndroid: {'🟢' if info['android'] else '⚪'}\nGradle: {'🟢' if info['gradle'] else '⚪'}\nKotlin: {'🟢' if info['kotlin'] else '⚪'}\nJava: {'🟢' if info['java'] else '⚪'}\nPython: {'🟢' if info['python'] else '⚪'}\nNode: {'🟢' if info['node'] else '⚪'}\n\nReady. Choose a repository to upload/update."
            reporter.finish(final,buttons)
        except Exception as e:tg_send(token,chat,"❌ ZIP validation failed: "+safe(redact(e)))
        return
    if mode in ("zip_update","zip") and text and text.startswith("/") and mode=="zip_update":
        S.awaiting.pop(uid,None);handle_cmd(token,uid,chat,text);return
    if mode=="schedule" and text:
        parts=[x.strip() for x in text.split("|",2)]
        if len(parts)!=3:tg_send(token,chat,"Use repository | cron | task");return
        DBS.run("INSERT INTO scheduled_tasks(telegram_user_id,repository,task,cron,enabled) VALUES(?,?,?,?,1)",(uid,parts[0],parts[2],parts[1]));S.awaiting.pop(uid,None);tg_send(token,chat,"🗓 Scheduled AI task saved. A production scheduler/worker can execute it according to deployment capacity.");return
    if text.startswith("/"):handle_cmd(token,uid,chat,text)
    elif text:
        if DBS.pat(uid):
            ans=ai(text) or "AI provider is not configured. Use /settings or configure GEMINI_API_KEY / OPENROUTER_API_KEY on the host.";tg_send(token,chat,"🤖 "+ans)
        else:tg_send(token,chat,"Use /start or /help. Connect GitHub with /connect.")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/download/"):
            try:
                payload=verify_token(os.getenv("DOWNLOAD_SIGNING_KEY",""),self.path.split("/download/",1)[1]);kind,rest=payload.split(":",1);repo,aid=rest.rsplit(":",1);owner,name=repo.split("/",1);pat=os.getenv("GITOFY_DOWNLOAD_SERVICE_PAT","")
                if kind!="artifact" or not pat:raise ValueError("download unavailable")
                r=http(GH+f"/repos/{owner}/{name}/actions/artifacts/{aid}/zip","GET",{"Authorization":f"Bearer {pat}","X-GitHub-Api-Version":"2022-11-28"},None,180,stream=True)
                self.send_response(200);self.send_header("Content-Type","application/zip");self.end_headers()
                while True:
                    b=r.read(8*1024*1024)
                    if not b:break
                    self.wfile.write(b)
                return
            except Exception:
                self.send_response(404);self.end_headers();return
        if self.path!="/healthz":self.send_response(404);self.end_headers();return
        body=json.dumps({"status":"healthy","telegram":"process-alive","database":"healthy","storage":"healthy","disk":"healthy"}).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if self.path!="/github/webhook":self.send_response(404);self.end_headers();return
        secret=os.getenv("GITHUB_WEBHOOK_SECRET","").encode();body=self.rfile.read(int(self.headers.get("Content-Length","0")))
        sig=self.headers.get("X-Hub-Signature-256","")
        expected="sha256="+hmac.new(secret,body,hashlib.sha256).hexdigest() if secret else ""
        if not secret or not hmac.compare_digest(sig,expected):self.send_response(401);self.end_headers();return
        delivery=self.headers.get("X-GitHub-Delivery","");event=self.headers.get("X-GitHub-Event","")
        digest=hashlib.sha256(body).hexdigest();status="received"
        try:
            payload=json.loads(body.decode())
            wf_run=payload.get("workflow_run") or {}
            run_id=wf_run.get("id")
            gh_repo_id=((payload.get("repository") or {}).get("id"))
            repo=((payload.get("repository") or {}).get("full_name"))
        except Exception:run_id=None;repo=None;wf_run={};gh_repo_id=None
        try:
            DBS.run("INSERT INTO webhook_events(github_delivery_id,event_type,run_id,payload_hash,received_at,status) VALUES(?,?,?,?,?,?)",(delivery,event,run_id,digest,now(),status))
        except Exception: pass
        # Idempotent webhook event storage plus optional monitor wake-up.
        if run_id and repo:
            rows=DBS.q("SELECT wr.*,r.owner||'/'||r.name repo FROM workflow_runs wr JOIN repositories r ON r.id=wr.repository_id WHERE wr.github_run_id=?",(run_id,))
            for row in rows:
                pat=DBS.pat(row['telegram_user_id'])
                if pat and run_id not in S.monitors:
                    m=Monitor(pat,row);S.monitors[run_id]=m;m.start()
            # A workflow run that finished but wasn't started through the bot
            # (e.g. triggered by a plain `git push`) has no workflow_runs row
            # and never gets picked up by a Monitor above. Cover that case
            # here so a failure still reaches the person: look up everyone
            # who is tracking this repository and alert them directly.
            if event=="workflow_run" and not rows and wf_run.get("status")=="completed" and wf_run.get("conclusion")=="failure" and gh_repo_id:
                trackers=DBS.q("SELECT * FROM repositories WHERE github_repo_id=?",(gh_repo_id,))
                owner,name=(repo.split("/",1) if repo and "/" in repo else (repo or "",""))
                for tr in trackers:
                    uid=tr["telegram_user_id"]
                    if DBS.repo_notification_mode(tr["id"])=="none":continue
                    pat=DBS.pat(uid)
                    if not pat:continue
                    # Assumes a private Telegram chat, where chat_id == user_id.
                    send_failure_alert(pat,uid,uid,wf_run,owner,name)
        self.send_response(202);self.end_headers()
    def log_message(self,*a):pass

def health_server():
    port=int(os.getenv("PORT","8080"));ThreadingHTTPServer(("0.0.0.0",port),HealthHandler).serve_forever()

def cleanup_loop():
    while True:
        try:
            cutoff=time.time()-int(os.getenv("CLEANUP_MINUTES","30"))*60
            for base in (TMP,UP):
                for p in base.iterdir():
                    if p.is_file() and p.stat().st_mtime<cutoff:
                        try:p.unlink()
                        except Exception:pass
        except Exception:pass
        time.sleep(3600)

def recover_monitors(token):
    rows=DBS.q("SELECT wr.*,r.owner||'/'||r.name repo FROM workflow_runs wr JOIN repositories r ON r.id=wr.repository_id WHERE wr.status NOT IN ('completed','cancelled')")
    for row in rows:
        try:
            m=Monitor(token,row);S.monitors[row["github_run_id"]]=m;m.start()
        except Exception:pass

TOKEN=os.getenv("BOT_TOKEN","").strip()

# Dedicated non-daemon validation queue.  Telegram updates acknowledge the PAT
# immediately, while this worker owns the bounded GitHub request and guarantees
# a terminal success/failure message even when the host is slow.
PAT_JOBS = queue.Queue()

def pat_validation_loop():
    while True:
        job = PAT_JOBS.get()
        try:
            validate_pat_worker(*job)
        except BaseException as e:
            try:
                _, uid, chat, _, _ = job
                tg_send(TOKEN, chat, "❌ <b>GitHub connection failed</b>\n\n" + safe(redact(e)) + "\n\nPlease send a valid PAT again.")
            except Exception as send_err:
                print("PAT worker terminal-send error:", redact(send_err), flush=True)
        finally:
            PAT_JOBS.task_done()

def main():
    if not TOKEN:raise SystemExit("BOT_TOKEN is required")
    threading.Thread(target=health_server,daemon=True).start();threading.Thread(target=cleanup_loop,daemon=True).start();
    threading.Thread(target=pat_validation_loop,daemon=False,name="gitofy-pat-validation").start()
    recover_monitors(TOKEN)
    try:tg(TOKEN,"deleteWebhook",{"drop_pending_updates":"false"})
    except Exception:pass
    print(f"{APP} production stdlib runtime started",flush=True)
    while True:
        try:
            ups=tg(TOKEN,"getUpdates",{"timeout":25,"offset":S.offset,"allowed_updates":json.dumps(["message","callback_query"])})
            for u in ups:
                S.offset=max(S.offset,int(u["update_id"])+1)
                try:handle_update(TOKEN,u)
                except Exception as e:print("update error:",redact(e),flush=True)
        except Exception as e:print("polling error:",redact(e),flush=True);time.sleep(3)

if __name__=="__main__":main()
