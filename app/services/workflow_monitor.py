import asyncio
import logging

log = logging.getLogger(__name__)


class WorkflowMonitor:
    """Poll one GitHub Actions run and continuously edit one Telegram message.

    The monitor never requires a manual Refresh. Every poll fetches the run and
    its jobs/steps. Telegram edit failures are retried without stopping the
    monitor, and terminal state is always rendered once before returning.
    """

    async def monitor(self, gh, owner, name, run_id, update=None,
                      initial=2, maximum=2):
        delay = max(1, int(initial or 2))
        last_signature = None
        last_good = None

        while True:
            try:
                run = await gh.run(owner, name, run_id)
                jobs_response = await gh.jobs(owner, name, run_id)
                jobs = jobs_response.get('jobs', []) if isinstance(jobs_response, dict) else []

                signature = self._signature(run, jobs)
                # Update immediately on the first poll and on every actual
                # GitHub state transition. The caller edits the same message.
                if update and (last_signature is None or signature != last_signature):
                    try:
                        await update(run, jobs)
                    except Exception:
                        # Rendering/Telegram failures must not kill monitoring.
                        log.exception('workflow Telegram update failed')

                last_signature = signature
                last_good = (run, jobs)

                if run.get('status') == 'completed':
                    # The completion transition above already triggers update().
                    # Do not send a duplicate edit for the same state.
                    return run, jobs

            except asyncio.CancelledError:
                raise
            except Exception:
                # Keep polling through transient GitHub/API errors. If we have a
                # previous good state, the Telegram message remains useful instead
                # of being replaced by a misleading error.
                log.exception('workflow polling failed')

            await asyncio.sleep(delay)

    @staticmethod
    def _signature(run, jobs):
        return (
            run.get('id'), run.get('status'), run.get('conclusion'),
            run.get('run_attempt'),
            tuple(
                (j.get('id'), j.get('name'), j.get('status'), j.get('conclusion'),
                 tuple((s.get('number'), s.get('name'), s.get('status'), s.get('conclusion'))
                       for s in (j.get('steps') or [])))
                for j in jobs
            )
        )
