# Zosimix

**An agent that repairs mixes it can't hear, and a benchmark that proves it.**

Zosimix gives Claude a way to "hear" a multitrack mix through measurement tools. It lets Claude repair the problems it finds inside FL Studio, and it measures how well each repair worked. The test set is made of faults injected into professional multitrack recordings, so the correct answer is always known.

> **Status:** building (day 11 of the plan). The harness, the benchmark, the FL Studio engine and its parity check against the offline engine all work ([results/parity.md](results/parity.md)). Latest full evaluation, 30 tasks × 3 repeats on Sonnet 5.5: the harness passes 51%, plain Claude Code 34% and the existing FL Studio MCP 13% ([results/full-v2.md](results/full-v2.md)).

- [DESIGN.md](DESIGN.md): architecture, benchmark design, grading, and plan
- [docs/decisions.md](docs/decisions.md): every design decision, with the alternatives considered and the reasons for the choice

The benchmark uses [MoisesDB](https://github.com/moises-ai/moises-db) (Pereira et al., 2023) and [AlbumDB](https://doi.org/10.5281/zenodo.19683001) (McKenzie et al., 2026). Full citations are in [CITATIONS.md](CITATIONS.md).

Designed by me and implemented by directing [Claude Code](https://claude.com/claude-code). The process, from design to decision log to review, is part of the project.

The name comes from Zosimos of Panopolis, an early alchemist who wrote about distillation and the equipment used to purify impure material.
