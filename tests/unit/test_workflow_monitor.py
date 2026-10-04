import asyncio
from app.services.workflow_monitor import WorkflowMonitor


class FakeGH:
    def __init__(self):
        self.i = 0
    async def run(self, owner, name, run_id):
        self.i += 1
        return {'id': run_id, 'status': 'completed' if self.i >= 2 else 'in_progress', 'conclusion': 'success' if self.i >= 2 else None}
    async def jobs(self, owner, name, run_id):
        if self.i >= 2:
            return {'jobs': [{'id': 1, 'status': 'completed', 'conclusion': 'success', 'steps': [{'number': 1, 'status': 'completed', 'conclusion': 'success'}]}]}
        return {'jobs': [{'id': 1, 'status': 'in_progress', 'conclusion': None, 'steps': [{'number': 1, 'status': 'in_progress', 'conclusion': None}]}]}


def test_monitor_updates_automatically_without_refresh():
    seen = []
    async def update(run, jobs):
        seen.append((run['status'], jobs[0]['steps'][0]['status']))

    async def main():
        return await WorkflowMonitor().monitor(FakeGH(), 'o', 'n', 7, update=update, initial=1, maximum=1)

    final, jobs = asyncio.run(main())
    assert final['status'] == 'completed'
    assert seen == [('in_progress', 'in_progress'), ('completed', 'completed')]
