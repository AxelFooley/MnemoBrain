# Upgrading

Engines are pinned by env vars; MnemoBrain never moves a pin on its own.

## Backup first

```sh
mnemobrain stop gbrain
cp -a "$MNEMOBRAIN_HOME" "$MNEMOBRAIN_HOME.bak-$(date +%Y%m%d)"
```

A format migration inside either engine is one-way; the only cheap rollback is
a byte copy made before the upgrade.

## Upgrade one engine

Bump the pin, install, restart:

```sh
export MNEMOBRAIN_MNEMOSYNE_VERSION="3.16.0"   # or:
export MNEMOBRAIN_GBRAIN_REF="v0.51.0.0"
mnemobrain install
mnemobrain start gbrain
```

## After a gbrain upgrade: reindex

GBrain keeps derived indexes next to its pages. After any gbrain version jump,
rebuild them before trusting queries:

```sh
HOME="$MNEMOBRAIN_HOME" "$MNEMOBRAIN_HOME/node_modules/.bin/gbrain" reindex
```

(gbrain has no path flags; it always operates on `$HOME/.gbrain`, so the
launcher's HOME isolation is what points it at this stack.)

## Verify

```sh
mnemobrain doctor        # expect: 0 fail
```

Then query a page you know exists and compare the answer to what you expect.
Only then delete the backup.

## Rollback

Stop gbrain, restore the backup directory, re-export the previous pins, re-run
`mnemobrain install`, `mnemobrain start gbrain`, `mnemobrain doctor`.

## Hard-won notes

- A doctor FAIL on `mnemosyne` usually means the wrong interpreter is active:
  the check reads the venv that the `mnemobrain` binary itself runs from.
- If `install` re-downloads gbrain on every run, you changed
  `MNEMOBRAIN_GBRAIN_REF` — that is a real upgrade, do the backup step first.
