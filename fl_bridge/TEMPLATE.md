# Building the Zosimix24 FL template (one time, about 15 minutes)

**Shortcut:** a built copy is committed as `fl_bridge/Zosimix24.flp`. Copy it to `C:\zosimix\fl\Zosimix24.flp`, create the placeholders (below), and skip to "If the bridge doesn't answer". The steps below explain how it was built.

FL Studio's scripting API can't load audio or open projects, so FL needs one project built by hand. Every song uses this same project: the harness swaps the audio files it points to before FL opens it (D55).

The finished project has:
- **24 audio clips**, each placed at the very start of the song, and each pointing to `C:\zosimix\fl\slots\slotNN.wav`
- **Clip N routed to mixer insert N**
- **Fruity Parametric EQ 2** in the first effect slot of inserts 1–24
- **Nothing on the master**, and every fader, pan and knob left at its default

## Before you start
1. Make sure loopMIDI is running with the `Zosimix In` and `Zosimix Out` ports. FL's MIDI settings should still be set up from the spike.
2. Create the placeholder audio files. These are 24 silent 5-minute WAVs, about 630 MB in total:
   ```powershell
   .venv\Scripts\python -m zosimix.fl.slots placeholders
   ```

## Steps in FL Studio 20.9.2
1. **Start an empty project:** **File → New from template → Minimal → Empty**.
   - The usual default template puts a **Fruity Limiter on the master**. Open the mixer, click **Master**, and make sure its effect slots are empty.
2. **Add the 24 clips.** In File Explorer, open `C:\zosimix\fl\slots`, select `slot01.wav` through `slot24.wav`, and drag them all onto the **Playlist** at the very start (bar 1).
   - They should land on 24 separate playlist tracks, one per file, all starting at bar 1.
   - If they stack up or land elsewhere, drag each clip so it starts exactly at bar 1, one per track. Turn snap on ("Bar") so nothing is offset.
   - Check that the **Channel rack** lists them in order: slot01, slot02, … slot24.
3. **Route clip N to insert N.**
   - In the Channel rack, select all 24 audio channels. Click the first, then shift-click the last.
   - Open the Mixer and click **Insert 1**.
   - Press **Ctrl+Shift+L** ("Link selected channels → starting from this track"). slot01 now feeds Insert 1, slot02 feeds Insert 2, and so on.
4. **Add the EQ.** On each of **Insert 1 to Insert 24**, put **Fruity Parametric EQ 2** in the **first effect slot**. Leave it at its default (flat) setting.
5. **Leave everything else at its default:** faders, pans, the stereo separation knobs, and the channel volume and pan knobs. Don't rename anything; the harness names the inserts after the stems itself.
6. **Save** the project as `C:\zosimix\fl\Zosimix24.flp`. Use **File → Save as**, and type the path exactly.
7. **Reload the bridge script.** The bridge script was updated with commands for track names and stereo separation. Use one of these:
   - In **View → Script output**, pick the Zosimix tab and click **Reload script**.
   - Or restart FL.

Then tell Claude it's done. Leave FL open with this project: the next step reads FL's own value ranges through the bridge.

## If the bridge doesn't answer
Open **Options → MIDI settings**.
- **Input:** `Zosimix In` is enabled, its controller type is **Zosimix Bridge (user)**, and its port number is set (for example 200).
- **Output:** FL gives the `Zosimix In` output the same port number by itself and replies there. That is fine: the harness listens on both ports (D58). You can't remove it; FL puts it back at every start.
- The harness checks these settings before it starts FL (`zosimix.fl.session.check_midi_settings`) and says what is wrong.
