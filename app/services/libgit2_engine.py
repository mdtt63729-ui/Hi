"""Optional libgit2/pygit2 engine.

Gitofy never installs native dependencies at runtime.  If pygit2 is present on the
host, this engine is used for clone/index/commit/push operations.  Otherwise callers
must use their API fallback.  This keeps TheHostServer startup safe while allowing
high-performance native Git when libgit2 is available.
"""
from pathlib import Path
import os, shutil, tempfile

try:
    import pygit2  # type: ignore
except Exception:  # pragma: no cover
    pygit2 = None


def available() -> bool:
    return pygit2 is not None


class LibGit2Engine:
    def __init__(self, token: str):
        if pygit2 is None:
            raise RuntimeError("pygit2/libgit2 is not installed on this host")
        self.token = token

    def _callbacks(self, progress=None):
        def transfer(stats):
            if progress:
                total = getattr(stats, "total_objects", 0) or 0
                received = getattr(stats, "received_objects", 0) or 0
                percent = (received / total * 100.0) if total else None
                progress(received, total, percent)
        return pygit2.RemoteCallbacks(
            credentials=lambda url, username_from_url, allowed: pygit2.UserPass("x-access-token", self.token),
            transfer_progress=transfer,
        )

    def clone(self, owner, name, branch, destination, progress=None):
        url = f"https://github.com/{owner}/{name}.git"
        return pygit2.clone_repository(url, str(destination), checkout_branch=branch,
                                       callbacks=self._callbacks(progress))

    def sync_existing(self, owner, name, branch, source_root, progress=None, message="chore: replace project via Gitofy"):
        with tempfile.TemporaryDirectory(prefix="gitofy-libgit2-") as td:
            repo = self.clone(owner, name, branch, td, progress)
            root = Path(td)
            gitdir = root / ".git"
            for p in list(root.iterdir()):
                if p == gitdir:
                    continue
                if p.is_dir(): shutil.rmtree(p)
                else: p.unlink()
            src = Path(source_root)
            files = [p for p in src.rglob("*") if p.is_file()]
            for i, p in enumerate(files, 1):
                rel = p.relative_to(src)
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
                if progress: progress(i, len(files), i / len(files) * 100 if files else 100)
            index = repo.index
            index.read()
            index.add_all()
            index.write()
            tree = index.write_tree()
            sig = repo.default_signature
            repo.create_commit(f"refs/heads/{branch}", sig, sig, message, tree, [repo.head.target])
            remote = repo.remotes["origin"]
            remote.push([f"refs/heads/{branch}:refs/heads/{branch}"], callbacks=self._callbacks(progress))
            return repo.head.target

    def fresh_commit_and_push(self, owner, name, branch, source_root, progress=None, message="chore: upload project via Gitofy"):
        # For an empty/new repository. Creates a local repository with a single root commit.
        with tempfile.TemporaryDirectory(prefix="gitofy-libgit2-new-") as td:
            root = Path(td)
            repo = pygit2.init_repository(str(root), False)
            src = Path(source_root)
            files = [p for p in src.rglob("*") if p.is_file()]
            for i, p in enumerate(files, 1):
                rel = p.relative_to(src); target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, target)
                if progress: progress(i, len(files), i / len(files) * 100 if files else 100)
            repo.index.add_all(); repo.index.write(); tree = repo.index.write_tree()
            sig = repo.default_signature
            commit = repo.create_commit("HEAD", sig, sig, message, tree, [])
            remote = repo.remotes.create("origin", f"https://github.com/{owner}/{name}.git")
            remote.push([f"HEAD:refs/heads/{branch}"], callbacks=self._callbacks(progress))
            return commit
