"""Everything that talks to FL Studio 20.9.2 (DESIGN.md §3.3, D55).

  bridge    - the client side of the SysEx bridge (the server side is fl_bridge/device_Zosimix.py)
  slots     - the fixed WAV paths the hand-built template points to, and writing a song into them
  session   - launch FL on a copy of the template, save, close, and render from the command line
  controls  - FL's knob positions <-> the units FL reports (dB, Hz, named choices)
  probe     - calibration step 1: read FL's own value scales through the bridge
  calibrate - calibration step 2: measure what the controls do to sound, with renders
"""
