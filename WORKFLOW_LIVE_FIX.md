# Gitofy v38 — Live Workflow Monitoring Fix

## Fixed
- Workflow dispatch now records the latest run ID **before** dispatching.
- The bot waits for a genuinely new run instead of accidentally monitoring an older completed run returned by GitHub immediately after dispatch.
- The first real run state and current jobs/steps are rendered immediately.
- The same Telegram message is edited automatically every time GitHub reports a run/job/step state transition.
- Polling remains fixed at 2 seconds; no manual Refresh is required.
- Transient GitHub/API/Telegram edit failures no longer terminate the monitor.
- Step signatures include job/step names and status/conclusion so UI updates cannot be missed when only a step changes.
- Terminal state is updated exactly once on the completed transition, avoiding duplicate Telegram edits.

## User-visible flow
1. Run workflow.
2. Gitofy shows the actual new run.
3. Jobs and steps appear as soon as GitHub exposes them.
4. `🔄` changes to `✅`/`❌` automatically in the same message.
5. Progress and current step update automatically.
6. No Refresh button is required.
