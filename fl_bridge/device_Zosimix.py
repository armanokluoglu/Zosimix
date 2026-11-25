# name=Zosimix Bridge
# url=https://github.com/armanokluoglu/Zosimix
"""Zosimix bridge: the small script that runs INSIDE FL Studio.

FL Studio runs this file in its own embedded, stripped-down Python (3.9 on FL 20.9.2).
That interpreter has no json, no sockets, no threads and no third-party packages, so
this file deliberately stays dumb: it parses one plain-text command, calls FL's API,
and replies. All the real logic lives in the external Zosimix code.

Transport: MIDI SysEx over two loopMIDI virtual ports.
  request : F0 7D 5A <ascii text> F7     (7D = "non-commercial" manufacturer ID, 5A = 'Z')
  reply   : F0 7D 5A <ascii text> F7
Text format: "<id> <command> <args...>" -> "<id> ok <values...>" or "<id> err <message>".
The id lets the client match replies to requests.

Indices follow FL's API: mixer track 0 is Master, 1.. are inserts; slot 0 is the
first effect slot; parameter values are normalized floats in 0..1.
"""

import device
import general
import midi
import mixer
import plugins
import transport

HEADER = bytes([0xF0, 0x7D, 0x5A])


def _reply(text):
    device.midiOutSysex(HEADER + text.encode("ascii", "replace") + bytes([0xF7]))


def _cmd_ping(args):
    return ["pong", str(general.getVersion())]


def _cmd_get_volume(args):
    return [repr(mixer.getTrackVolume(int(args[0])))]


def _cmd_set_volume(args):
    mixer.setTrackVolume(int(args[0]), float(args[1]))
    return [repr(mixer.getTrackVolume(int(args[0])))]          # read back what FL actually holds


def _cmd_get_volume_db(args):
    return [repr(mixer.getTrackVolume(int(args[0]), 1))]       # mode 1 = dB (added in 20.9)


def _cmd_get_pan(args):
    return [repr(mixer.getTrackPan(int(args[0])))]


def _cmd_set_pan(args):
    mixer.setTrackPan(int(args[0]), float(args[1]))
    return [repr(mixer.getTrackPan(int(args[0])))]


def _cmd_get_polarity(args):
    return [str(int(mixer.isTrackRevPolarity(int(args[0]))))]


def _cmd_set_polarity(args):
    # Always pass the value explicitly: called without one it sets False instead of toggling.
    mixer.revTrackPolarity(int(args[0]), bool(int(args[1])))
    return [str(int(mixer.isTrackRevPolarity(int(args[0]))))]


def _cmd_get_sep(args):
    return [repr(mixer.getTrackStereoSep(int(args[0])))]


def _cmd_set_sep(args):
    mixer.setTrackStereoSep(int(args[0]), float(args[1]))
    return [repr(mixer.getTrackStereoSep(int(args[0])))]


def _cmd_get_name(args):
    return [mixer.getTrackName(int(args[0])).replace(" ", "_") or "-"]


def _cmd_set_name(args):
    # Names arrive without spaces (they are split on spaces); underscores are kept as-is.
    mixer.setTrackName(int(args[0]), args[1] if len(args) > 1 else "")
    return [mixer.getTrackName(int(args[0])).replace(" ", "_") or "-"]


def _cmd_plugin_name(args):
    track, slot = int(args[0]), int(args[1])
    if not plugins.isValid(track, slot):
        return ["none"]
    return [plugins.getPluginName(track, slot).replace(" ", "_")]


def _cmd_param_count(args):
    return [str(plugins.getParamCount(int(args[0]), int(args[1])))]


def _cmd_param_info(args):
    track, slot, param = int(args[0]), int(args[1]), int(args[2])
    name = plugins.getParamName(param, track, slot).replace(" ", "_") or "-"
    value = plugins.getParamValue(param, track, slot)
    try:
        shown = plugins.getParamValueString(param, track, slot).replace(" ", "_") or "-"
    except Exception:
        shown = "-"
    return [name, repr(value), shown]


def _cmd_set_param(args):
    track, slot, param, value = int(args[0]), int(args[1]), int(args[2]), float(args[3])
    plugins.setParamValue(value, param, track, slot)
    return [repr(plugins.getParamValue(param, track, slot))]


def _cmd_save(args):
    transport.globalTransport(midi.FPT_Save, 1)
    return ["saved"]


COMMANDS = {
    "ping": _cmd_ping,
    "get_volume": _cmd_get_volume,
    "set_volume": _cmd_set_volume,
    "get_volume_db": _cmd_get_volume_db,
    "get_pan": _cmd_get_pan,
    "set_pan": _cmd_set_pan,
    "get_polarity": _cmd_get_polarity,
    "set_polarity": _cmd_set_polarity,
    "get_sep": _cmd_get_sep,
    "set_sep": _cmd_set_sep,
    "get_name": _cmd_get_name,
    "set_name": _cmd_set_name,
    "plugin_name": _cmd_plugin_name,
    "param_count": _cmd_param_count,
    "param_info": _cmd_param_info,
    "set_param": _cmd_set_param,
    "save": _cmd_save,
}


def OnInit():
    print("Zosimix bridge ready, API version", general.getVersion())


def OnSysEx(event):
    data = bytes(event.sysex)
    if not data.startswith(HEADER):
        return                                    # not ours: let FL handle it
    event.handled = True
    parts = data[len(HEADER):-1].decode("ascii", "replace").split()
    if len(parts) < 2:
        return
    req_id, name, args = parts[0], parts[1], parts[2:]
    handler = COMMANDS.get(name)
    if handler is None:
        _reply(req_id + " err unknown_command")
        return
    try:
        _reply(req_id + " ok " + " ".join(handler(args)))
    except Exception as exc:
        _reply(req_id + " err " + type(exc).__name__ + ":" + str(exc).replace(" ", "_"))
