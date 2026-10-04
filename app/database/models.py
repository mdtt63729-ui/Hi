from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, Text, DateTime, BigInteger, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def now(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__='users'; id:Mapped[int]=mapped_column(Integer,primary_key=True); telegram_id:Mapped[int]=mapped_column(BigInteger,unique=True,index=True); username:Mapped[str|None]=mapped_column(String(255)); status:Mapped[str]=mapped_column(String(32),default='active'); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class GitHubConnection(Base):
    __tablename__='github_connections'; id:Mapped[int]=mapped_column(Integer,primary_key=True); telegram_user_id:Mapped[int]=mapped_column(BigInteger,index=True); github_user_id:Mapped[int|None]=mapped_column(BigInteger); github_username:Mapped[str|None]=mapped_column(String(255)); encrypted_pat:Mapped[str]=mapped_column(Text); token_type:Mapped[str|None]=mapped_column(String(32)); permissions:Mapped[dict]=mapped_column(JSON,default=dict); status:Mapped[str]=mapped_column(String(32),default='active'); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class Repository(Base):
    __tablename__='repositories'; __table_args__=(UniqueConstraint('telegram_user_id','github_repo_id'),); id:Mapped[int]=mapped_column(Integer,primary_key=True); telegram_user_id:Mapped[int]=mapped_column(BigInteger,index=True); github_repo_id:Mapped[int]=mapped_column(BigInteger); owner:Mapped[str]=mapped_column(String(255)); name:Mapped[str]=mapped_column(String(255)); default_branch:Mapped[str]=mapped_column(String(255),default='main'); visibility:Mapped[str|None]=mapped_column(String(32)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class RepositorySettings(Base):
    __tablename__='repository_settings'; repository_id:Mapped[int]=mapped_column(ForeignKey('repositories.id'),primary_key=True); default_branch:Mapped[str|None]=mapped_column(String(255)); default_workflow:Mapped[str|None]=mapped_column(String(255)); auto_build:Mapped[bool]=mapped_column(Boolean,default=False); sync_mode:Mapped[str]=mapped_column(String(16),default='update'); notification_mode:Mapped[str]=mapped_column(String(32),default='all')
class Operation(Base):
    __tablename__='operations'; id:Mapped[str]=mapped_column(String(64),primary_key=True); telegram_user_id:Mapped[int]=mapped_column(BigInteger,index=True); repository_id:Mapped[int|None]=mapped_column(Integer); branch:Mapped[str|None]=mapped_column(String(255)); type:Mapped[str]=mapped_column(String(64)); status:Mapped[str]=mapped_column(String(32)); progress:Mapped[float]=mapped_column(default=0); worker_id:Mapped[str|None]=mapped_column(String(128)); error_code:Mapped[str|None]=mapped_column(String(128)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class WorkflowRun(Base):
    __tablename__='workflow_runs'; id:Mapped[int]=mapped_column(Integer,primary_key=True); repository_id:Mapped[int]=mapped_column(Integer); github_run_id:Mapped[int]=mapped_column(BigInteger,index=True); workflow_id:Mapped[int|None]=mapped_column(BigInteger); branch:Mapped[str|None]=mapped_column(String(255)); status:Mapped[str|None]=mapped_column(String(32)); conclusion:Mapped[str|None]=mapped_column(String(32)); last_checked:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); monitoring_mode:Mapped[str|None]=mapped_column(String(32)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class WebhookEvent(Base):
    __tablename__='webhook_events'; id:Mapped[int]=mapped_column(Integer,primary_key=True); github_delivery_id:Mapped[str]=mapped_column(String(255),unique=True,index=True); event_type:Mapped[str]=mapped_column(String(64)); repository_id:Mapped[int|None]=mapped_column(Integer); run_id:Mapped[int|None]=mapped_column(BigInteger); payload_hash:Mapped[str]=mapped_column(String(128)); received_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); processed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); status:Mapped[str]=mapped_column(String(32),default='received')
class Artifact(Base):
    __tablename__='artifacts'; id:Mapped[int]=mapped_column(Integer,primary_key=True); repository_id:Mapped[int]=mapped_column(Integer); github_artifact_id:Mapped[int]=mapped_column(BigInteger,index=True); name:Mapped[str]=mapped_column(String(512)); size:Mapped[int|None]=mapped_column(BigInteger); expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); run_id:Mapped[int|None]=mapped_column(BigInteger); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class UserSession(Base):
    __tablename__='user_sessions'; id:Mapped[int]=mapped_column(Integer,primary_key=True); telegram_user_id:Mapped[int]=mapped_column(BigInteger,index=True); state:Mapped[str]=mapped_column(String(64)); data:Mapped[dict]=mapped_column(JSON,default=dict); expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
class ActivityHistory(Base):
    __tablename__='activity_history'; id:Mapped[int]=mapped_column(Integer,primary_key=True); telegram_user_id:Mapped[int]=mapped_column(BigInteger,index=True); action:Mapped[str]=mapped_column(String(255)); details:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class AIProviderCredential(Base):
    __tablename__='ai_provider_credentials'
    provider:Mapped[str]=mapped_column(String(32),primary_key=True)
    encrypted_api_key:Mapped[str]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)

class AIUserPreference(Base):
    __tablename__='ai_user_preferences'
    telegram_user_id:Mapped[int]=mapped_column(BigInteger,primary_key=True)
    mode:Mapped[str]=mapped_column(String(32),default='auto')
    model:Mapped[str|None]=mapped_column(String(255),nullable=True)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)

class AIMemory(Base):
    __tablename__='ai_memory'; id:Mapped[int]=mapped_column(Integer,primary_key=True); repository_id:Mapped[int]=mapped_column(Integer,index=True); key:Mapped[str]=mapped_column(String(255)); value:Mapped[str]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class AuditLog(Base):
    __tablename__='audit_logs'; id:Mapped[int]=mapped_column(Integer,primary_key=True); operation_id:Mapped[str]=mapped_column(String(64),index=True); telegram_user_id:Mapped[int]=mapped_column(BigInteger,index=True); user_request:Mapped[str]=mapped_column(Text); ai_decision:Mapped[str]=mapped_column(Text); tool:Mapped[str]=mapped_column(String(255)); repository:Mapped[str|None]=mapped_column(String(512)); target:Mapped[str|None]=mapped_column(String(1024)); action:Mapped[str]=mapped_column(String(255)); result:Mapped[str]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class ScheduledAITask(Base):
    __tablename__='scheduled_ai_tasks'; id:Mapped[int]=mapped_column(Integer,primary_key=True); telegram_user_id:Mapped[int]=mapped_column(BigInteger,index=True); name:Mapped[str]=mapped_column(String(255)); command:Mapped[str]=mapped_column(Text); interval_seconds:Mapped[int]=mapped_column(Integer); enabled:Mapped[bool]=mapped_column(Boolean,default=True); next_run:Mapped[datetime]=mapped_column(DateTime(timezone=True)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class AITaskRun(Base):
    __tablename__='ai_task_runs'; id:Mapped[int]=mapped_column(Integer,primary_key=True); task_id:Mapped[int]=mapped_column(Integer,index=True); status:Mapped[str]=mapped_column(String(32)); result:Mapped[dict]=mapped_column(JSON,default=dict); started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); finished_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
