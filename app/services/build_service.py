from datetime import datetime,timezone
TERMINAL={'success','failure','cancelled','skipped','neutral'}
def user_status(run):
    c=run.get('conclusion'); s=run.get('status')
    if c=='success': return '🟢 Success'
    if c in ('failure','timed_out'): return '🔴 Failed'
    if c=='cancelled': return '⚪ Cancelled'
    if s=='queued': return '🟡 Queued'
    return '🔵 Running'
def run_progress(jobs):
    total=completed=0; current=''
    for j in jobs:
        for st in j.get('steps') or []:
            total+=1
            if st.get('status')=='completed': completed+=1
            elif st.get('status')=='in_progress': current=st.get('name','')
    return completed,total,current
