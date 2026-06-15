# test-tools

A collection of standalone test tools for TR4W development. Each tool lives in
its own subfolder and is self-contained — kept here, separate from the main
[TR4W/TR4W](https://github.com/TR4W/TR4W) repository, so it isn't pulled down
with the application.

## Tools

| Tool | Description |
|------|-------------|
| [`mockDXCluster/`](mockDXCluster/) | A DX cluster simulator: a telnet server that streams synthetic AK1A-style DX spots, for exercising logging/contest software against a cluster feed offline. |
