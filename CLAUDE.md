# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`TR4W/test-tools` is a collection of standalone test tools for TR4W development.
It is kept separate from the main [`TR4W/TR4W`](https://github.com/TR4W/TR4W)
application repo so these tools are not pulled down with the app. Each tool lives
in its own self-contained subfolder; add a new tool as a sibling subfolder and a
row in the root `README.md` table.

Repo-wide files (`LICENSE`, `.gitignore`, `README.md`, this file) live at the
root; everything else belongs to a specific tool's subfolder.

## mockDXCluster

A single-file Python DX cluster simulator (`mockDXCluster/mockDXCluster.py`,
stdlib only, Python 3.8+). It is a port of the C# `ClusterSimulator` and must
stay behavior-compatible with it. It listens on a TCP port and streams synthetic
AK1A-style "DX spots" to connected telnet clients, for exercising
logging/contest software against a cluster feed offline.

### Running

```sh
python3 mockDXCluster/mockDXCluster.py    # start the server (Ctrl+C to stop)
telnet localhost 2323                     # connect a client to verify
```

There is no test suite; verify by connecting and watching the spot stream, or by
driving it from a script over a socket.

### Architecture

`MockDXCluster` (one class) is the whole tool. `start()` runs a blocking accept
loop; each connection gets its own daemon `Thread` running `_handle_client`,
which sends telnet negotiation, a banner, then loops emitting one `_random_spot`
every `interval_ms`. Inbound bytes are read only when `select` reports data
ready, cleaned of telnet IAC sequences (`_clean_telnet_input`), and dispatched
through `_process_command` (`help`/`time`/`uptime`/`echo`/`own`/`notown`/`bye`).

### Configuration

Read from `~/.config/mockDXCluster.ini` (single `[mockDXCluster]` section). Keys:
`port`, `own_call`, `own_frequency`, `own_spots`, `interval_ms`. A missing file
or any malformed value falls back to the built-in `DEFAULTS` dict, so the tool
runs with zero config. The committed `mockDXCluster.ini.sample` is the template;
the real `mockDXCluster.ini` is gitignored and must never be committed.

### Behavior worth knowing before editing

- **`own_spots` is process-global, shared across all client threads.** The
  `own` / `notown` commands flip the feed for *every* connected client, not just
  the caller. It is guarded by a lock (`_own_lock`); keep access going through
  the `own_spots` property rather than touching `_own_spots` directly.
- **One shared `random.Random` (`self._rng`).** Deliberately not re-seeded per
  call. Do not replace it with module-level `random.*` from threads without
  considering that the instance is shared; the original C# bug was constructing
  a fresh time-seeded RNG per call, which repeated values in tight loops.
- **The spot line is fixed-width AK1A format.** The field widths in the
  `_random_spot` f-string match real cluster output and the reference lines in
  its docstring — do not "tidy" the spacing.
- **Keep parity with the C# original** (`ClusterSimulator/Program.cs`). Any
  change to spot format or the command set should be mirrored there.
