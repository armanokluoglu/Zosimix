# Building an eval for an agent that can't hear

Claude can read, write and run code, but it can't listen to audio. So I asked a narrow question: if you hand Claude Code the separate tracks of a song, one of them deliberately damaged, can it find the problem and fix it the way a mix engineer would? And what does it take to make it good at that?

This post covers the project that came out of it, [Zosimix](https://github.com/armanokluoglu/Zosimix). It has two parts: a Claude Code plugin that gives the agent something like ears, and the benchmark I built to check whether the plugin works. The benchmark taught me more than the plugin did. I designed it and directed the work; Claude Code wrote the code.

## The setup

A mix is a set of stems (vocals, kick, snare, bass, guitars), each with a fader, a pan, maybe an EQ. I took professionally mixed multitracks from two open datasets, MoisesDB and AlbumDB, and planted one fault per task in one stem:

- a gain change;
- a pan;
- a flipped drum mic;
- a resonant EQ boost;
- low-mid "mud";
- clipping baked into the recording;
- or nothing at all, as a control.

Because I planted the fault, the right answer is always known. Each task can come with a vague client note ("the mix feels muddy") or with none.

Grading is deterministic, with no LLM judge. A run passes if the agent names the right fault on the right stem, removes at least 70% of the fault-specific error, and leaves every healthy stem unchanged. Clipping can't be repaired, so there the right answer is to report it and touch nothing.

Three setups, same model (Claude Sonnet 5.5), same tasks:

- **The Zosimix harness:** Claude Code plus an MCP server of measurement tools, a diagnosis playbook (a skill), and a rule that changes have to be committed, and their effect reported, before the agent can submit.
- **Plain Claude Code:** file tools and a Python environment with the same audio libraries. It can write its own analysis code. It just has no mixing knowledge built in.
- **flstudio-mcp:** an existing open-source plugin that connects Claude to FL Studio's mixer and meters.

## The first run, and the benchmark's own bug

The first full run looked encouraging: the harness passed 47% of runs, plain Claude Code 30%. Then I looked at the breakdown. On mud and resonance, **both** setups scored zero: not one pass in 27 attempts each.

When everything fails on a category, the first suspect is the benchmark. I measured what the injected faults actually did to the mix. A "severe" 9 dB mud boost moved the mix's low-mid balance by a median of 0.25 dB, far below what anyone could hear. Two things caused it:

- The stem was often a small part of the mix: an outro guitar that plays for 15% of the song.
- Resonance frequencies were drawn anywhere in a stem's range, often in a dip between harmonics, where a boost has nothing to ring with.

So I changed what "severity" means. A mud or resonance fault is now sized by how much it changes the **mix**: 1, 2 or 3 dB for mud, 2, 4 or 6 dB for resonance. The generator solves for the filter gain that achieves that, and refuses stems too quiet to carry it. That's the version of the benchmark everything after this point uses.

The lesson I took from it: an eval can be broken in ways that look exactly like a weak agent. Check the benchmark before you tune the system.

## 51% and an honest way to improve it

On the corrected benchmark the harness passed 51%, plain Claude Code 37%, and flstudio-mcp 13%. flstudio-mcp's agent can read levels, but not spectra, stereo balance or phase, so most faults are invisible to it.

51% didn't feel like a result worth showing, but the easy way to raise it is the dishonest one: look at the failures, patch them, rerun the same tasks. I set three rules instead:

1. **Tune only on a separate development set.** I downloaded two more songs that never appear in the test.
2. **Find out what's findable at all.** I wrote an "oracle" check: for each task, does the relevant measurement rank the faulty stem first among all stems? It showed which failures were the agent's fault and which were the measurement's. Clipping and polarity were always findable, so those failures were about agent behaviour. A 3 dB gain change, by contrast, can't be singled out without a reference mix, so that's a real ceiling.
3. **Measure the final version on songs nobody tuned on.**

The development set turned up some concrete wins:

- **Resonance depth.** The playbook said to cut a resonance by the height the tool reported. But the detector measures a bump against its surroundings, which understates a boost by about half. Following the old advice repaired 11% of injected resonances even with the right stem; cutting twice the reported height repaired 78%.
- **Asking the mix, not the stem.** Ranking stems by "which one carries this band in the mix" found the faulty stem first in 24 of 24 injected mud faults, against 21% for the stem's own shape. The same idea worked for resonance. There's a caveat I state wherever I report it: the benchmark sizes these faults by their effect on the mix, which flatters a mix-based ranking. Real mixes won't be that clean.
- **A `triage` tool** that runs every objective check in one call. The agent had been skipping cheap checks when no client note pointed at them: it passed polarity when the client said the drums sounded thin, and failed both polarity tasks without a note.

And some setbacks:

- **New tools surfaced natural features.** A ranking that put the most prominent resonance at the top also put a guitar's natural 732 Hz body resonance there, and the agent "fixed" it on two healthy mixes. Some stem always tops a ranking. The fix was to treat taste-based faults (mud and resonance) as faults only when the client mentions them.
- **The grader had a bug of its own.** It measured mud repair as a band's share of the stem's energy, and a share flattens out when the band already dominates. On a snare, a 10 dB boost moved it by 0.1 dB, so any slightly imperfect cut scored as damage. I switched it to "band against the rest of the stem", regraded every stored answer, and flagged it in the commit as an eval-integrity change.

## Two results I didn't expect

**A stronger model didn't help.** I ran Claude Opus 5.5 with the same harness on 12 tasks: 58%, exactly what Sonnet scored on those tasks. On this problem the tools matter more than the model.

**A tool the agent never uses measures nothing.** I added a spectrogram picture (Claude can read images) and ran it as an ablation. The agent called it 0 times in 30 runs: the playbook described a workflow without it, and the agent follows the playbook. The tool only got used once the skill said when to look at it.

## The fix that backfired

On one test song, the toms and an acoustic guitar are mono parts panned to the side on purpose. That's exactly what my "mistaken pan" check looks for, so the agent re-centred them, on two healthy mixes among others. The obvious fix was "only act on a lean without a note if the stem belongs in the centre, or if the whole mix leans that way". I labelled it as test-informed and ran it.

The score went down, from 20 of 30 to 18. That song's clean mix happens to lean toward its toms, so the "mix leans" test fired anyway, and the new gate blocked three real pan faults on non-centre stems. I reverted it.

The rule that held up came from the tuning data instead. In 8 of 9 songs, no clean stem has the mistaken-pan signature. In the ninth, there are **two** such stems, while an injected fault always produces exactly one. So a single stray mono part off centre is a mistake, and several mean the arrangement pans mono parts deliberately.

## The held-out result

Once the fixes were driven by test-set failures, the original test set had become a tuning set. So I downloaded six more AlbumDB songs, generated 30 tasks on them, committed the file, and didn't look at it until the end. Then I ran each task three times:

| Held-out songs, 3 repeats | Harness | Plain Claude Code |
|---|---|---|
| Pass rate, in scope | **81%** (95% interval 70–89%) | 54% (42–65%) |
| Pass rate, every task | 62% | 41% |
| Task by task | better on 10, worse on 2 (p ≈ 0.04) | |
| Output tokens per task | 812 | 2,482 |

"In scope" needs explaining, because it's a choice that affects the number. The harness is designed to treat mud and resonance as faults only when the client mentions them. Seven held-out tasks have such a fault and no note, and both setups left all seven alone, which is the designed behaviour. I leave those tasks out of the headline rate for both setups alike, and report the every-task rate next to it. With a client note, the harness passed 45 of 51 runs.

flstudio-mcp isn't in this table: the held-out songs have up to 35 tracks, and my FL template has 24 slots. Its earlier result stands at 15%.

## Do the graders agree with ears?

A number like "repair score 0.95" means nothing if a repaired mix still sounds wrong. So I built a blind A/B page: 24 pairs of 12-second, loudness-matched clips, including identical pairs and clean-versus-broken pairs as controls. Then I listened.

It was hard, and most differences were subtle. But the controls held: identical clips sounded identical, and clean beat badly broken every time. Every time the grader passed a repair, I couldn't tell it from the engineer's original mix (6 of 6).

The surprises were instructive. I preferred a snare with an added 5 kHz ring over its repairs, because a brighter top end can sound exciting over 12 seconds. And a cut on the wrong stem can still make a muddy mix sound better. "Sounds better" and "restored to the engineer's mix" aren't the same question. The grader asks the second, by design.

## What I'd tell someone building an agent eval

- **Measure the benchmark before the agent.** Two of my biggest findings were bugs in the eval (inaudible faults, a grader that flattened out), not in the agent.
- **Keep three sets:** one to tune on, one to check progress, one you don't touch until the end. Counting every task, the harness scored 67% on the set whose failures guided the tuning, and 62% on songs nobody tuned on. That closeness is the evidence the tuning generalised instead of fitting the test.
- **Report the uncomfortable numbers.** The fix that made things worse, the tool nobody called, the model upgrade that changed nothing: these are the parts that make the headline believable.
- **Give the agent measurements, not just access.** Plain Claude Code had the same audio libraries and could write any analysis it wanted. It used three times the tokens and scored 27 points lower.

## Try it

Zosimix installs as a Claude Code plugin:

```
/plugin install zosimix --marketplace armanokluoglu/Zosimix
```

Export your mixer tracks from FL Studio (File → Export → WAV, "Split mixer tracks"), then run `/zosimix:fix "<folder>" what sounds wrong`. Claude measures, explains what it found and what it left alone, and can put the fix into your open FL project after showing you a dry-run plan. The code, the decision log (over 80 entries) and every results page are in the [repository](https://github.com/armanokluoglu/Zosimix).

Designed by me, implemented by directing Claude Code.

## Data

The songs come from MoisesDB and AlbumDB.

## MoisesDB

- License: CC BY-NC-SA 4.0 (non-commercial; derivatives must use the same license)
- Source: https://music.ai/research/ · https://github.com/moises-ai/moises-db

```bibtex
@misc{pereira2023moisesdb,
  title={Moisesdb: A dataset for source separation beyond 4-stems},
  author={Igor Pereira and Felipe Araújo and Filip Korzeniowski and Richard Vogl},
  year={2023},
  eprint={2307.15913},
  archivePrefix={arXiv},
  primaryClass={cs.SD}
}
```

## AlbumDB

- License: CC BY 4.0
- Source: https://doi.org/10.5281/zenodo.19683001

```bibtex
@dataset{mckenzie_2026_19683001,
  author    = {McKenzie, Thomas and Moliner Juanpere, Eloi and Wright, Alec},
  title     = {AlbumDB: A multitrack dataset of a ten-song album with stereo and immersive 7.1.4 masters},
  month     = apr,
  year      = 2026,
  publisher = {Zenodo},
  version   = {1.0},
  doi       = {10.5281/zenodo.19683001},
  url       = {https://doi.org/10.5281/zenodo.19683001}
}
```
