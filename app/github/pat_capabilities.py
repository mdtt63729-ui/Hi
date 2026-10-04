"""GitHub PAT capability catalog and runtime diagnostics.

The catalog deliberately distinguishes classic PAT scopes from fine-grained
permissions. A token never gains permissions because Gitofy lists a feature;
GitHub remains the authority and endpoint failures are surfaced honestly.
"""
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class Capability:
    key: str
    title: str
    classic: str
    fine_grained: str
    group: str

CAPABILITIES = [
    Capability('repositories','Repositories / code / contents','repo','Metadata + Contents (read/write) + Administration for destructive/settings actions','Repository'),
    Capability('repo_status','Commit / CI Status','repo:status','Commit statuses (read/write)','Repository'),
    Capability('deployments','Deployment status','repo_deployment','Deployments (read/write)','Repository'),
    Capability('public_repo','Public repositories','public_repo','Metadata + Contents on selected public repositories','Repository'),
    Capability('repo_invite','Repository invitations','repo:invite','Administration / repository invitations as supported','Repository'),
    Capability('security_events','Security events / code scanning / secret scanning','security_events','Security events / code scanning / secret scanning permissions as applicable','Security'),
    Capability('actions','GitHub Actions / workflow files','workflow','Actions + workflow permissions as required','Automation'),
    Capability('packages_write','Publish packages','write:packages','Packages: write (where supported)','Packages'),
    Capability('packages_read','Read packages','read:packages','Packages: read (where supported)','Packages'),
    Capability('packages_delete','Delete packages','delete:packages','Packages: delete/admin (where supported)','Packages'),
    Capability('org_admin','Organization administration','admin:org','Organization Administration (write)','Organization'),
    Capability('org_write','Organization membership/projects','write:org','Organization Members/Projects (write)','Organization'),
    Capability('org_read','Organization membership/teams','read:org','Organization Members/Teams (read)','Organization'),
    Capability('repo_hooks_admin','Repository webhooks full control','admin:repo_hook','Repository Hooks (read/write)','Hooks'),
    Capability('repo_hooks_write','Repository webhooks write','write:repo_hook','Repository Hooks (write)','Hooks'),
    Capability('repo_hooks_read','Repository webhooks read','read:repo_hook','Repository Hooks (read)','Hooks'),
    Capability('org_hooks','Organization webhooks','admin:org_hook','Organization Hooks (write)','Hooks'),
    Capability('public_keys_admin','Public keys full control','admin:public_key','Public Keys / Administration','Account'),
    Capability('public_keys_write','Public keys write','write:public_key','Public Keys (write)','Account'),
    Capability('public_keys_read','Public keys read','read:public_key','Public Keys (read)','Account'),
    Capability('gpg_keys_admin','GPG keys full control','admin:gpg_key','GPG Keys / Administration','Account'),
    Capability('gpg_keys_write','GPG keys write','write:gpg_key','GPG Keys (write)','Account'),
    Capability('gpg_keys_read','GPG keys read','read:gpg_key','GPG Keys (read)','Account'),
    Capability('profile','User profile read/write','user','Account/Profile permissions where supported','Account'),
    Capability('profile_read','User profile read','read:user','Account/Profile read','Account'),
    Capability('email','User email','user:email','Account email access where supported','Account'),
    Capability('follow','Follow / unfollow users','user:follow','Not generally available as a fine-grained PAT permission','Account'),
    Capability('projects','Projects','project','Projects permissions; user-owned Projects have fine-grained limitations','Projects'),
    Capability('projects_read','Projects read','read:project','Projects read permissions','Projects'),
    Capability('notifications','Notifications / subscriptions','notifications','Notifications access where supported','Account'),
    Capability('gists','Gists','gist','Gists access where supported','Gists'),
    Capability('codespaces','Codespaces lifecycle','codespace','Codespaces permissions where supported','Codespaces'),
    Capability('audit','Organization audit log','read:audit_log','Organization Audit Log read','Enterprise / Audit'),
    Capability('enterprise_admin','Enterprise administration','admin:enterprise','Enterprise Administration where supported','Enterprise / Audit'),
    Capability('enterprise_runners','Enterprise self-hosted runners','manage_runners:enterprise','Enterprise Runners / Administration','Enterprise / Audit'),
    Capability('enterprise_billing','Enterprise billing','manage_billing:enterprise','Enterprise Billing / Administration','Enterprise / Audit'),
    Capability('enterprise_read','Enterprise profile','read:enterprise','Enterprise read','Enterprise / Audit'),
    Capability('delete_repo','Delete repositories','delete_repo','Repository Administration (write)','Repository'),
    Capability('issues','Issues / comments / labels','repo','Issues (read/write)','Repository'),
    Capability('pull_requests','Pull requests / reviews / merge','repo','Pull requests (read/write)','Repository'),
    Capability('releases','Releases / tags','repo','Contents + Metadata / Releases as required','Repository'),
    Capability('search','Repository / code search','repo or public access','Metadata / Contents depending on endpoint','Repository'),
    Capability('secrets','Repository / environment secrets','repo / workflow as applicable','Actions secrets / Environments secrets (write)','Automation'),
    Capability('variables','Repository / environment variables','repo / workflow as applicable','Actions variables / Environments variables (write)','Automation'),
    Capability('environments','Environments / deployment protection','repo','Environments (read/write)','Deployments'),
    Capability('rulesets','Rulesets / branch protection','repo','Administration / Rulesets permissions','Repository'),
    Capability('discussions','Discussions','repo','Discussions (read/write)','Repository'),
    Capability('offline_access','OAuth refresh/offline access','offline_access','N/A for PAT','OAuth'),
]


def classic_scope_set(scopes: Iterable[str]) -> set[str]:
    return {s.strip() for s in scopes if s and s.strip()}


def classic_available(cap: Capability, scopes: set[str]) -> bool:
    if not scopes:
        return False
    wanted = {x.strip() for x in cap.classic.split('/')}
    # Some entries are alternatives; repo/public_repo also cover many read operations.
    if cap.key in {'public_repo','repo_status','deployments','issues','pull_requests','releases','search'} and 'repo' in scopes:
        return True
    if cap.key == 'public_repo' and 'public_repo' in scopes:
        return True
    if cap.key == 'repositories' and ('repo' in scopes or 'public_repo' in scopes):
        return True
    return bool(wanted & scopes)


def render_report(scopes: Iterable[str], fine_grained: bool = False) -> str:
    scopes = classic_scope_set(scopes)
    lines = ['🔐 <b>GitHub PAT Capability Report</b>', '']
    if fine_grained:
        lines += ['Token type: <b>Fine-grained PAT</b>', 'GitHub is the authority for each endpoint permission.', '']
    else:
        lines += ['Token type: <b>Classic PAT</b>', 'Detected scopes: <code>' + ', '.join(sorted(scopes)) + '</code>', '']
    groups = []
    for c in CAPABILITIES:
        if c.group not in groups: groups.append(c.group)
    for g in groups:
        lines.append(f'<b>{g}</b>')
        for c in CAPABILITIES:
            if c.group != g: continue
            ok = '🟢' if (not fine_grained and classic_available(c, scopes)) else ('🔵' if fine_grained else '⚪')
            lines.append(f'{ok} {c.title}')
        lines.append('')
    lines.append('ℹ️ A listed capability is not a permission grant. If GitHub returns 403, Gitofy reports the missing/required permission instead of pretending access exists.')
    return '\n'.join(lines)
