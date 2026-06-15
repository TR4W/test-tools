# mockDXCluster

A DX cluster simulator for amateur radio. It emulates an AK1A-style DX cluster
node: telnet clients that connect receive a continuous stream of synthetic
"DX spots". It lets you exercise logging/contest software (such as TR4W) against
a cluster feed without a live internet connection to a real node.

This is a single-file Python port of the original C# `ClusterSimulator`.

## Requirements

Python 3.8+. Standard library only — no third-party packages.

## Running

```sh
python3 mockDXCluster.py
```

The server listens on port 2323 by default. Connect a client to verify:

```sh
telnet localhost 2323
```

It begins streaming spot lines immediately. Stop the server with Ctrl+C.

## Configuration

Settings are read from `~/.config/mockDXCluster.ini`. If the file (or any
individual key) is missing, built-in defaults are used, so the simulator runs
with no configuration at all.

Copy [`mockDXCluster.ini.sample`](mockDXCluster.ini.sample) to
`~/.config/mockDXCluster.ini` and edit it. Available keys: `port`, `own_call`,
`own_frequency`, `own_spots`, `interval_ms`.

## Interactive commands

Once connected, clients can type:

| Command          | Effect                                  |
|------------------|-----------------------------------------|
| `help`           | Show the command list                   |
| `time`           | Show current server time                |
| `uptime`         | Show how long the server has been up    |
| `echo <message>` | Echo a message back                     |
| `own`            | Switch the feed to own-station spots    |
| `notown`         | Switch the feed back to random spots    |
| `bye`            | Disconnect                              |

`own` / `notown` change the feed for **all** connected clients, not just the
caller.
