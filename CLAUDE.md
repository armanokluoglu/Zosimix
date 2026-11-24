# Zosimix: instructions for Claude Code

Read [DESIGN.md](DESIGN.md) and [docs/decisions.md](docs/decisions.md) before starting any work.

## Who builds this
The owner designs the project and directs the work. Claude Code writes the code. The owner reads the code at each milestone and asks questions, so:
- Write clean, plain, explainable Python. Avoid clever tricks. Add a short docstring that says *why* wherever the reason isn't obvious.
- Every non-trivial choice made during implementation gets a new entry at the bottom of `docs/decisions.md`. Never edit old entries; supersede them with a new one.

## Hard rules
- **Eval integrity (DESIGN.md §4.8):** the agent under test must never be able to read ground truth. Any change to graders, the task generator, or the ground-truth layout must be called out in the commit message.
- **Budget:** Claude Pro only. Never add Anthropic API-key usage. Never pass `--bare` to `claude -p`.
- **No dataset audio in git.** Ship download scripts and task definitions only.
- **Cite the datasets.** Any README, blog post, results page or video that uses MoisesDB or AlbumDB data must cite them exactly as in [CITATIONS.md](CITATIONS.md). Every song's `song.json` carries its attribution.
- **FL Studio target is Producer 20.9.2.** The script that runs inside FL uses its embedded Python 3.9, so no 3.10+ syntax and no third-party imports there. Keep that script minimal and put all logic in the external Python code.

## Conventions
- Python 3.12+ outside FL, managed with uv. Lint with ruff, test with pytest.
- Windows is the primary platform (FL Studio and loopMIDI).
