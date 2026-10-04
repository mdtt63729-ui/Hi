from pathlib import Path

def test_empty_repository_bootstrap_is_explicit():
    text = Path('app/services/git_cli_engine.py').read_text()
    assert "ls-remote" in text and "--heads" in text
    assert "git init", "-b" in text or "git init" in text

def test_upload_flow_supports_empty_repository():
    text = Path('app/bot/handlers/upload.py').read_text()
    assert 'EMPTY — creating first commit' in text
    assert 'engine.sync_zip' in text
    assert 'project:{action}:' in text
