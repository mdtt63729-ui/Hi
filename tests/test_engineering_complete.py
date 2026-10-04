import pytest
from app.engineering.permissions import PermissionPolicy
from app.engineering.agent import AutonomousEngineer,AgentContext
from app.engineering.knowledge import RepoKnowledge
from app.engineering.testing import TestAgent
from app.engineering.dependency import DependencyIntelligence
from app.engineering.review import CodeReviewer
from app.engineering.formatting import TelegramFormatter
from app.engineering.acceptance import evaluate

def test_dangerous_requires_confirmation():
 d=PermissionPolicy().decide('repo.delete'); assert d.requires_confirmation
 assert PermissionPolicy().decide('repo.delete',True).allowed

def test_knowledge_search_and_dependencies():
 files={'app/Main.kt':'class Main { fun login() = Unit }','build.gradle.kts':'implementation("a:b:1-SNAPSHOT")'}
 k=RepoKnowledge('x'); k.index(files); assert 'app/Main.kt' in k.search('login'); assert DependencyIntelligence().scan(files)

def test_test_agent_and_review():
 files={'app/Main.kt':'class Main { }','app/Secrets.kt':'val token = "secret"'}
 assert TestAgent().inspect(files); assert CodeReviewer().review(files)

def test_progress_is_actual():
 assert TelegramFormatter().progress(5,10).endswith('50%)')

def test_acceptance_is_explicit():
 x=evaluate({k:True for k in __import__('app.engineering.acceptance',fromlist=['ACCEPTANCE']).ACCEPTANCE}); assert all(x.values())
