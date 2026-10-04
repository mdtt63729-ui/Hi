# GitHub PAT capability matrix

Gitofy treats GitHub as the permission authority. A PAT cannot be elevated by the bot.

## Classic PAT / OAuth-style scopes supported by GitHub

- `repo` — full repository access and related repository resources
- `repo:status` — commit statuses
- `repo_deployment` — deployment statuses
- `public_repo` — public repositories
- `repo:invite` — repository invitations
- `security_events` — code/secret scanning security events
- `admin:repo_hook`, `write:repo_hook`, `read:repo_hook` — repository hooks
- `admin:org`, `write:org`, `read:org` — organization administration/membership/projects
- `admin:public_key`, `write:public_key`, `read:public_key` — SSH/public keys
- `admin:org_hook` — organization hooks
- `gist` — gists
- `notifications` — notifications and thread subscriptions
- `user`, `read:user`, `user:email`, `user:follow` — profile/email/follow
- `project`, `read:project` — Projects
- `delete_repo` — delete repositories the user can administer
- `write:packages`, `read:packages`, `delete:packages` — GitHub Packages
- `admin:gpg_key`, `write:gpg_key`, `read:gpg_key` — GPG keys
- `codespace` — Codespaces
- `workflow` — GitHub Actions workflow files
- `admin:enterprise`, `manage_runners:enterprise`, `manage_billing:enterprise`, `read:enterprise` — enterprise administration
- `read:audit_log` — audit log
- `offline_access` — OAuth refresh/offline access; not a normal PAT repository permission

## Gitofy API coverage

Gitofy exposes wrappers for repository contents/trees/refs, repository settings and deletion, branches, collaborators, hooks, deploy keys, commit statuses/checks, deployments, Actions/workflows/runs/jobs/logs/artifacts, repository secrets/variables metadata, environments, rulesets, issues, pull requests, releases, search, organizations/members/teams, organization hooks and Actions permissions, runners, packages/version metadata, notifications, gists, keys, GPG keys, Codespaces lifecycle, audit logs, enterprise reads, starring/following, and discussions.

The UI includes a PAT Capability Report. For classic PATs it reads `X-OAuth-Scopes`; for fine-grained PATs it does not pretend that classic scopes exist and relies on GitHub endpoint permissions.

## Important limitation

Fine-grained PATs do not support every classic-PAT feature. GitHub documents gaps including Packages, Checks API, some Projects scenarios, outside-collaborator access and multi-organization access. Use the GitHub endpoint's required-permission response when a capability is denied.
