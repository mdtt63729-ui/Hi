"""Git smart-HTTP engine used when libgit2/pygit2 is unavailable.

This is intentionally a subprocess wrapper around the system Git client.  It
avoids GitHub's REST Git-Data API blob-per-file pattern, which is the source of
secondary-rate-limit failures on large projects.  Git's smart HTTP protocol
packs objects and transfers them in a small number of requests.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile


def available() -> bool:
    return shutil.which("git") is not None


class GitCliEngine:
    def __init__(self, token: str):
        if not available():
            raise RuntimeError("system git is not installed on this host")
        self.token = token

    def _env(self, askpass: Path) -> dict:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = str(askpass)
        env["SSH_ASKPASS"] = str(askpass)
        env["GITOFY_ASKPASS_TOKEN"] = self.token
        return env

    @staticmethod
    def _run(args, cwd=None, env=None, progress=None, timeout=1800):
        # --progress writes transfer progress to stderr even when stderr is not
        # a TTY.  We parse Git's object-count percentages without blocking the
        # Telegram operation on API edits.
        proc = subprocess.Popen(
            args, cwd=str(cwd) if cwd else None, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        last_pct = None
        lines = []
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            lines.append(line.rstrip())
            if progress:
                m = re.search(r"(\d+)%", line)
                if m:
                    pct = max(0, min(100, int(m.group(1))))
                    if pct != last_pct:
                        last_pct = pct
                        progress(pct)
        proc.wait(timeout=timeout)
        if proc.returncode != 0:
            tail = "\n".join(lines[-12:])
            # Never leak the PAT if Git includes an authenticated URL/error.
            tail = tail.replace(os.environ.get("GITOFY_ASKPASS_TOKEN", ""), "[REDACTED]")
            raise RuntimeError(f"git command failed ({proc.returncode}): {tail[-2500:]}")
        return lines

    def _askpass(self, td: Path) -> Path:
        p = td / "askpass.sh"
        p.write_text(
            '#!/bin/sh\n'
            'case "$1" in\n'
            '  *Username*) printf "%s\\n" "x-access-token" ;;\n'
            '  *) printf "%s\\n" "$GITOFY_ASKPASS_TOKEN" ;;\n'
            'esac\n',
            encoding="utf-8",
        )
        p.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return p

    @staticmethod
    def _extract_zip(path: str, root: Path):
        with ZipFile(path) as z:
            names = [x.filename.replace("\\", "/").lstrip("/")
                     for x in z.infolist() if x.filename and not x.is_dir()]
            names = [n for n in names if not n.startswith(".git/")]
            tops = {n.split("/", 1)[0] for n in names}
            strip = next(iter(tops)) if len(tops) == 1 and all("/" in n for n in names) else ""
            total = 0
            files = 0
            for item in z.infolist():
                n = item.filename.replace("\\", "/").lstrip("/")
                if not n or n.endswith("/") or n.startswith(".git/"):
                    continue
                rel = n[len(strip) + 1:] if strip and n.startswith(strip + "/") else n
                if not rel or rel.startswith(".git/"):
                    continue
                target = (root / rel).resolve()
                if root.resolve() not in target.parents:
                    raise RuntimeError("unsafe ZIP path")
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out, 4 * 1024 * 1024)
                files += 1
                total += item.file_size
        return files, total

    def sync_zip(self, owner, name, branch, zip_path, progress=None,
                 message="chore(gitofy): replace project from ZIP [skip ci]"):
        with tempfile.TemporaryDirectory(prefix="gitofy-git-") as td:
            base = Path(td)
            askpass = self._askpass(base)
            env = self._env(askpass)
            root = base / "repo"
            remote = f"https://github.com/{owner}/{name}.git"

            # A shallow clone is enough: we preserve the current branch history
            # while avoiding downloading an entire multi-year repository.
            cloned = False
            # Empty repositories have no branch/ref to clone. Probe first so
            # authentication/network errors are not mistaken for an empty repo.
            probe = subprocess.run(
                ["git", "ls-remote", "--heads", remote],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", timeout=120,
            )
            if probe.returncode != 0:
                err = probe.stderr.replace(self.token, "[REDACTED]")
                raise RuntimeError(f"Unable to access GitHub repository: {err[-1200:]}")
            if not probe.stdout.strip():
                root.mkdir(parents=True, exist_ok=True)
                self._run(["git", "init", "-b", branch], cwd=root, env=env)
                self._run(["git", "remote", "add", "origin", remote], cwd=root, env=env)
            else:
                self._run(["git", "clone", "--depth=1", "--single-branch",
                           "--branch", branch, remote, str(root)], env=env)
                cloned = True

            deleted = 0
            if cloned:
                # Count tracked files before replacement, then remove every
                # project file but keep .git.
                try:
                    tracked = self._run(["git", "ls-files", "-z"], cwd=root, env=env)
                    deleted = len([x for x in "\n".join(tracked).split("\0") if x])
                except Exception:
                    deleted = 0
                for p in list(root.iterdir()):
                    if p.name == ".git":
                        continue
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()

            if progress:
                progress(2)
            files, total_bytes = self._extract_zip(zip_path, root)
            if progress:
                progress(25)

            self._run(["git", "add", "-A"], cwd=root, env=env)
            self._run(["git", "-c", "user.name=Gitofy", "-c",
                       "user.email=gitofy@users.noreply.github.com", "commit",
                       "--allow-empty", "-m", message], cwd=root, env=env)
            if progress:
                progress(35)

            # --progress makes the smart HTTP pack transfer report object-level
            # progress.  Unlike REST blob uploads, this is not one request per
            # source file and therefore scales much better for large projects.
            lines = self._run(["git", "push", "--progress", "origin",
                               f"HEAD:refs/heads/{branch}"], cwd=root, env=env,
                              progress=lambda p: progress(35 + p * 0.64) if progress else None)

            sha_lines = self._run(["git", "rev-parse", "HEAD"], cwd=root, env=env)
            sha = sha_lines[-1].strip() if sha_lines else ""
            return {"sha": sha, "files": files, "bytes": total_bytes, "deleted": deleted}

    def update_zip(self, owner, name, branch, zip_path, progress=None,
                   message="chore(gitofy): replace project from ZIP [skip ci]"):
        """Replace the branch working tree with the ZIP while preserving Git history."""
        with tempfile.TemporaryDirectory(prefix="gitofy-git-update-") as td:
            base=Path(td); askpass=self._askpass(base); env=self._env(askpass); root=base/'repo'
            remote=f"https://github.com/{owner}/{name}.git"
            self._run(["git","clone","--depth=1","--single-branch","--branch",branch,remote,str(root)],env=env)
            if progress: progress(5)
            before=set()
            try: before={x for x in self._run(["git","ls-files"],cwd=root,env=env) if x}
            except Exception: pass
            for p in list(root.iterdir()):
                if p.name=='.git': continue
                if p.is_dir(): shutil.rmtree(p)
                else: p.unlink()
            if progress: progress(15)
            files,total_bytes=self._extract_zip(zip_path,root)
            after={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and '.git' not in p.parts}
            deleted=sorted(before-after)
            added=sorted(after-before)
            modified=[]
            try:
                status=self._run(["git","status","--porcelain"],cwd=root,env=env)
                for line in status:
                    if line and line[0:2].strip() not in ('??','A') and line[:2].strip(): modified.append(line[3:] if len(line)>3 else line)
            except Exception: pass
            if progress: progress(35)
            self._run(["git","add","-A"],cwd=root,env=env)
            self._run(["git","-c","user.name=Gitofy","-c","user.email=gitofy@users.noreply.github.com","commit","--allow-empty","-m",message],cwd=root,env=env)
            if progress: progress(50)
            self._run(["git","push","--progress","origin",f"HEAD:refs/heads/{branch}"],cwd=root,env=env,progress=lambda p: progress(50+p*0.49) if progress else None)
            sha=self._run(["git","rev-parse","HEAD"],cwd=root,env=env)[-1].strip()
            return {'changed':True,'sha':sha,'files':files,'bytes':total_bytes,'deleted':len(deleted),'added':len(added),'modified':len(modified),'deleted_paths':deleted}

    def apply_file_changes(self, owner, name, branch, changes, message='fix(gitofy): AI build repair [skip ci]', progress=None):
        """Apply AI-generated changes to existing files, commit, and push."""
        with tempfile.TemporaryDirectory(prefix='gitofy-ai-fix-') as td:
            base=Path(td); askpass=self._askpass(base); env=self._env(askpass); root=base/'repo'
            remote=f'https://github.com/{owner}/{name}.git'
            self._run(['git','clone','--depth=1','--single-branch','--branch',branch,remote,str(root)],env=env)
            if progress: progress(40)
            changed=[]
            for change in changes:
                rel=str(change['path']).replace('\\','/')
                if rel.startswith('/') or rel.startswith('../') or '/..' in rel.split('/') or rel=='.git' or rel.startswith('.git/'):
                    raise RuntimeError('AI attempted to modify an unsafe repository path')
                target=(root/rel).resolve()
                if root.resolve() not in target.parents or not target.is_file():
                    raise RuntimeError(f'AI attempted to modify a non-existing file: {rel}')
                target.write_text(change['content'],encoding='utf-8'); changed.append(rel)
            if progress: progress(60)
            self._run(['git','add','--']+changed,cwd=root,env=env)
            status=self._run(['git','status','--porcelain'],cwd=root,env=env)
            if not status: return {'changed':False,'files':[],'sha':self._run(['git','rev-parse','HEAD'],cwd=root,env=env)[-1].strip()}
            self._run(['git','-c','user.name=Gitofy','-c','user.email=gitofy@users.noreply.github.com','commit','-m',message],cwd=root,env=env)
            if progress: progress(75)
            self._run(['git','push','--progress','origin',f'HEAD:refs/heads/{branch}'],cwd=root,env=env,progress=lambda p: progress(75+p*0.24) if progress else None)
            sha=self._run(['git','rev-parse','HEAD'],cwd=root,env=env)[-1].strip()
            return {'changed':True,'files':changed,'sha':sha,'count':len(changed)}
