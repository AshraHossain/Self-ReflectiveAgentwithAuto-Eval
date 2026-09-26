# EACP — Enterprise Agent Control Plane

Enterprise Agent Control Plane — one governance layer over LangGraph, CrewAI and ag2.

> Early development. This README currently documents installation and platform
> support only; the full overview, architecture and quickstart land later.

## Install

The core package depends on no agent framework. Each backend is an extra:

```bash
pip install eacp                 # core, framework-free — 17 packages
pip install 'eacp[langgraph]'    # + LangGraph backend  — 52 packages
pip install 'eacp[ag2]'          # + ag2 backend        — 25 packages
pip install 'eacp[crewai]'       # + CrewAI backend     — see platform support below
```

The full dependency graph is 172 packages, so a single-framework adopter installs
roughly a tenth of it. `import eacp` never imports an agent framework — adapters
load on demand when you ask for a backend.

The `ag2` extra installs the [`ag2`](https://pypi.org/project/ag2/) PyPI package —
**not** `autogen`, `pyautogen`, or `autogen-agentchat`, which are three different
codebases in the same lineage. There is no `eacp[autogen]` extra.

## Platform support

| Platform | `eacp` (core) | `eacp[langgraph]` | `eacp[ag2]` | `eacp[crewai]` |
|----------|:---:|:---:|:---:|:---:|
| Linux x86_64 | ✅ | ✅ | ✅ | ✅ |
| Linux aarch64 | ✅ | ✅ | ✅ | ✅ |
| macOS arm64 (Apple Silicon) | ✅ | ✅ | ✅ | ✅ |
| **macOS x86_64 (Intel)** | ✅ | ✅ | ✅ | ❌ **not supported** |
| Windows x86_64 | ✅ | ✅ | ✅ | ✅ (untested by this project) |

**macOS x86_64 (Intel) — `eacp[crewai]` is not installable.** `crewai>=1.15` requires
`lancedb>=0.29.2,<0.30.1`, and `lancedb` publishes **no** `macosx_*_x86_64` wheel in any
released version, and no source distribution — so there is nothing to build from source
either. This is an upstream packaging gap, not an EACP limitation, and we cannot work
around it. `eacp` core, `eacp[langgraph]` and `eacp[ag2]` all install and run normally on
Intel macOS; only the CrewAI extra is affected. Use Linux, macOS arm64, Windows, or a
Linux container to work with the CrewAI backend.

Verification status: the macOS x86_64 row is measured directly. The other rows are
inferred from `lancedb`'s published wheel tags (manylinux x86_64/aarch64,
`macosx_11_0_arm64`, `win_amd64`) and confirmed by CI rather than measured on the
author's host; the Windows row is untested by this project.

## Development

```bash
uv sync --locked                      # dev environment (dev group included)
uv sync --locked --no-default-groups  # exactly what `pip install eacp` gives a user
```

`uv.lock` is committed and hash-pinned; CI gates on `uv lock --check`.

## License

MIT — see [LICENSE](LICENSE).
