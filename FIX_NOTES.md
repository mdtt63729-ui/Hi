# Gitofy Upload / Update Fix

## Fixed ZIP upload stuck at 99%
The Telegram progress editor is now serialized with the final result edit. A queued or in-flight 99% progress edit can no longer overwrite the final Project Analysis / success message.

## Update Project is now a full replacement
`Update Project` now replaces the repository working tree with the uploaded ZIP. Files that exist in the repository but are missing from the new ZIP are removed. Git history is preserved through a normal commit.

## Progress display
The old horizontal line progress indicator was replaced with a real block-style progress bar using filled (`█`) and empty (`░`) segments.

## Regression tests
Added tests for the block progress bar and the stale-progress-edit race condition.
