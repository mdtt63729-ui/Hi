from app.engineering.acceptance import ACCEPTANCE, evaluate

def test_all_acceptance_items_are_registered():
    assert len(ACCEPTANCE)==30
    assert len(set(ACCEPTANCE))==30

def test_all_items_can_be_evaluated():
    result=evaluate({name: True for name in ACCEPTANCE})
    assert all(result.values())
