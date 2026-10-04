from aiogram.fsm.state import State,StatesGroup
class GitofyStates(StatesGroup):
    waiting_pat=State(); waiting_zip=State(); waiting_repo=State(); waiting_branch=State(); waiting_commit=State(); waiting_workflow_input=State(); waiting_confirmation=State(); ai_chat=State(); waiting_ai_key=State()
