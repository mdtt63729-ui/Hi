import os
from .libgit2_engine import available, LibGit2Engine

def native_available():
    return available()

def get_engine(token):
    preferred=os.getenv('GITOFY_GIT_ENGINE','auto').lower()
    if preferred in ('libgit2','pygit2') or (preferred=='auto' and available()):
        return LibGit2Engine(token)
    return None
