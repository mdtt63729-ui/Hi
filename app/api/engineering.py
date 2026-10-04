from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from app.engineering.agent import AutonomousEngineer,AgentContext
from app.engineering.permissions import PermissionPolicy
from app.engineering.automation import TaskScheduler
from app.engineering.telemetry import Telemetry
from app.engineering.nl_router import NaturalLanguageRouter

router=APIRouter(prefix='/engineering',tags=['engineering'])
agent=AutonomousEngineer(); scheduler=TaskScheduler(); telemetry=Telemetry(); nl=NaturalLanguageRouter()
class AnalyzeRequest(BaseModel): repository:str; error:str; files:dict[str,str]={}
class FixRequest(AnalyzeRequest): approved:bool=False; max_attempts:int=Field(3,ge=1,le=3)
class MaintenanceRequest(BaseModel): repository:str; files:dict[str,str]={}
class ScheduleRequest(BaseModel): user_id:int; name:str; command:str; interval_seconds:int=Field(...,ge=60)
class IntentRequest(BaseModel): text:str
@router.post('/diagnose')
def diagnose(x:AnalyzeRequest): return agent.diagnose(x.repository,x.error,x.files)
@router.post('/fix')
def fix(x:FixRequest): return agent.fix_and_verify(AgentContext(x.error,x.repository,approved=x.approved,max_attempts=x.max_attempts,files=x.files),x.error)
@router.post('/maintenance')
def maintenance(x:MaintenanceRequest): return agent.run_maintenance(AgentContext('maintenance',x.repository,files=x.files))
@router.post('/intent')
def intent(x:IntentRequest): return nl.parse(x.text).__dict__
@router.post('/schedule')
def schedule(x:ScheduleRequest): return scheduler.add(x.user_id,x.name,x.command,x.interval_seconds).__dict__
@router.get('/tasks')
def tasks(): return [x.__dict__ for x in scheduler.tasks.values()]
@router.get('/audit')
def audit(): return agent.audit.export_json()
@router.get('/telemetry')
def telemetry_snapshot(): return telemetry.snapshot()
