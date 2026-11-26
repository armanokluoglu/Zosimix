# Demo video plan (days 13–14)

**Goal:** 2–3 minutes that show the problem (Claude can't hear a mix), the harness working on one real fault, and the benchmark result. It sits at the top of the README (DESIGN.md §6). **Audio:** AlbumDB songs only (CC BY 4.0, DESIGN.md §3), with the attribution on screen at the end.

## Storyboard

| # | Shot (time) | What's on screen | How to get it |
|---|---|---|---|
| 1 | Hook (0:00–0:15) | Title: "Claude can't hear. Can it fix a mix?" over a waveform of the song | Any video editor |
| 2 | The fault (0:15–0:35) | A real multitrack in FL Studio; play 10 s of the broken mix (for example the hard-panned lead guitar of dev-003, or the 10 dB backing-vocal boost of full-v2-020) | Build the FL project with `FLEngine` on the broken stems, or play the listening clips |
| 3 | The agent at work (0:35–1:20) | Terminal: `claude -p` with the Zosimix tools. Show `triage` finding the fault, the `set_*` call, and `commit_changes` reporting what moved. Speed up 4× | `python -m zosimix.runner run --set dev --config zosimix --tasks dev-003 --run demo`; the transcript is `C:\zosimix\runs\demo\transcripts\*.jsonl` |
| 4 | The fix, heard (1:20–1:45) | Back in FL: the repaired project, with the changed setting visible (the pan knob or EQ band). Play the same 10 s, then broken against repaired | Render the agent's mix state with `FLEngine` and open the saved project in FL |
| 5 | The benchmark (1:45–2:20) | The results chart: harness 51%, plain Claude Code 37%, flstudio-mcp 13%. One line on how passes are graded | `results/chart.svg` |
| 6 | Credits (2:20–2:40) | "Designed by me, implemented by directing Claude Code." Repo link. AlbumDB citation (McKenzie, Moliner, Wright, 2026, CC BY 4.0) | CITATIONS.md |

## Notes

- Pick a fault you can hear on laptop speakers: a pan or a big gain fault, not subtle mud.
- Record FL and the terminal at 1080p. Keep the screen free of personal folders and the Windows user name: work from `C:\zosimix`.
- If time runs short, cut polish first (DESIGN.md §7): one take of shots 2–5, narrated, is enough.
- What's still needed: a small helper that opens the broken and the repaired project in FL for one task, so shots 2 and 4 don't need manual setup. `FLEngine` already writes and renders the project; it would only need to keep the project file and open it.
