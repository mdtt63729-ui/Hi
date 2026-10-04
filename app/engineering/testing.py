from dataclasses import dataclass
import re
@dataclass
class TestFinding:
 path:str; kind:str; detail:str; severity:str
class TestAgent:
 def inspect(self,files):
  findings=[]; test_files=[p for p in files if re.search(r'(^|/)(test|tests)(/|$)|Test\.',p,re.I)]
  source=[p for p in files if p.endswith(('.kt','.java','.py','.js','.ts')) and p not in test_files]
  if not test_files and source: findings.append(TestFinding('', 'missing_tests','No test files detected for source code.','medium'))
  for p in source:
   if len(files[p])>8000 and not any(p.rsplit('/',1)[-1].split('.')[0].lower() in t.lower() for t in test_files): findings.append(TestFinding(p,'untested_source','Large source file has no obvious matching test.','low'))
  return findings
 def generate_test_stub(self,path,language='kotlin'):
  name=re.sub(r'\.[^.]+$','',path).split('/')[-1]
  if language.lower()=='kotlin': return 'class '+name+'Test {\n    // TODO: add behavior-focused tests for '+name+'\n}'
  if language.lower()=='java': return f'class {name}Test {{\n    // TODO: add behavior-focused tests for {name}\n}}'
  return f'def test_{name.lower()}_placeholder():\n    assert True\n'
