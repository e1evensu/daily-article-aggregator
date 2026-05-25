# CodeGraph Notes

Source: https://github.com/colbymchenry/codegraph

Local checkout: `/home/suuuu/develop/codegraph`

Local CLI:

```bash
node /home/suuuu/develop/codegraph/dist/bin/codegraph.js
```

## Purpose

Use CodeGraph as the local, persistent code/document index for this project so future agent work can query project structure instead of repeatedly scanning files and consuming tokens.

## Project State

- `.codegraph/` has been initialized locally.
- This scaffold currently has no Go/Python source files, so there are no code symbols indexed yet.
- `.codegraph/` is intentionally ignored by Git because it contains local SQLite data.

## Common Commands

```bash
# Rebuild or initialize the local index
node /home/suuuu/develop/codegraph/dist/bin/codegraph.js init -i

# Incrementally sync after edits
node /home/suuuu/develop/codegraph/dist/bin/codegraph.js sync

# Inspect index status
node /home/suuuu/develop/codegraph/dist/bin/codegraph.js status

# Ask CodeGraph for task-oriented context
node /home/suuuu/develop/codegraph/dist/bin/codegraph.js context "describe the ingestion flow"
```

## Maintaining CodeGraph

Workspace helper:

```bash
/home/suuuu/develop/scripts/maintain-codegraph.sh
```

Manual steps:

```bash
cd /home/suuuu/develop/codegraph
git pull --ff-only
npm install
npm run build
```
