from .build_service import user_status, run_progress

def _step_icon(step):
    st=step.get('status') or 'queued'; con=step.get('conclusion')
    if con == 'success': return '✅'
    if con == 'failure': return '❌'
    if con == 'skipped': return '⏭️'
    if con == 'cancelled': return '⚪'
    if st == 'in_progress': return '🔄'
    return '⚪'

def render_workflow(run, jobs, *, title='Gitofy • Live Workflow'):
    completed,total,current=run_progress(jobs)
    lines=[f'⚙️ {title}',f'Workflow: {run.get("name") or run.get("workflow_name") or "GitHub Actions"}',f'Run: #{run.get("run_number") or run.get("id")}',f'Status: {user_status(run)}','']
    for ji,job in enumerate(jobs):
        jname=job.get('name','Job'); jstatus=job.get('status') or 'queued'; jcon=job.get('conclusion')
        jicon='✅' if jcon=='success' else ('❌' if jcon=='failure' else ('🔄' if jstatus=='in_progress' else '⚪'))
        lines.append(f'{jicon} {jname}')
        steps=job.get('steps') or []
        for si,step in enumerate(steps):
            icon=_step_icon(step); name=step.get('name','Step'); suffix='  ← running' if step.get('status')=='in_progress' else ''
            lines.append(f'{icon} {name}{suffix}')
            if si < len(steps)-1: lines.append('│')
        if ji < len(jobs)-1: lines.append('')
    if total:
        p=100 if run.get('conclusion')=='success' else min(99,int(completed/total*100))
        filled=int(24*p/100)
        lines += ['',f'Progress: {"█"*filled}{"░"*(24-filled)} {p}%  ({completed}/{total} steps)']
    if current: lines.append(f'Current: {current}')
    return '\n'.join(lines)[:4000]
