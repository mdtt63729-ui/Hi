from app.services.progress_service import ProgressService
def test_progress(): assert ProgressService().calc(5,10)==50.0
def test_unknown(): assert ProgressService().calc(0,0) is None
