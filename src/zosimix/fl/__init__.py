"""Everything that talks to FL Studio 20.9.2 (DESIGN.md §3.3, D55).

  bridge  - the client side of the SysEx bridge (the server side is fl_bridge/device_Zosimix.py)
  slots   - the fixed WAV paths the hand-built template points to, and writing a song into them
  render  - FL's command-line renderer, wrapped in a watchdog
"""
