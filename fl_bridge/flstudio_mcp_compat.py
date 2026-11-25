# Zosimix compatibility block for flstudio-mcp's FL script on FL Studio 20.9.2 (D66).
#
# FL 20.9.2's embedded Python 3.9 has no `json` and no `base64` module, and flstudio-mcp's
# FL script needs both for its protocol (base64-encoded JSON inside SysEx). This block
# provides exactly the four functions the script calls, with the same output as the
# standard library for the values the script sends. `binascii` does exist in FL 20.9.2,
# so base64 is just a thin wrapper. Pure Python 3.9, no other imports (no `re` either).
#
# zosimix.fl.port_flstudio_mcp pastes this block in place of the script's
# `import base64` / `import json` lines, after trying the real modules first.

import binascii as _binascii
import math as _math


class _Base64Compat:
    @staticmethod
    def b64encode(data):
        return _binascii.b2a_base64(bytes(data), newline=False)

    @staticmethod
    def b64decode(data):
        return _binascii.a2b_base64(bytes(data))


_ESCAPES = (('"', '\\"'), ("\\", "\\\\"), ("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t"), ("\b", "\\b"), ("\f", "\\f"))


class _JsonCompat:
    """json.dumps / json.loads for dicts, lists, str, int, float, bool and None."""

    @classmethod
    def _string(cls, s, ensure_ascii):
        escapes = dict(_ESCAPES)
        out = ['"']
        for ch in s:
            code = ord(ch)
            if ch in escapes:
                out.append(escapes[ch])
            elif code < 0x20:
                out.append(f"\\u{code:04x}")
            elif code > 0x7E and ensure_ascii:
                if code > 0xFFFF:                       # a surrogate pair, as json does
                    code -= 0x10000
                    out.append(f"\\u{0xD800 | (code >> 10):04x}\\u{0xDC00 | (code & 0x3FF):04x}")
                else:
                    out.append(f"\\u{code:04x}")
            else:
                out.append(ch)
        out.append('"')
        return "".join(out)

    @classmethod
    def _key(cls, key):
        if isinstance(key, str):
            return key
        if key is True:
            return "true"
        if key is False:
            return "false"
        if key is None:
            return "null"
        if isinstance(key, (int, float)):
            return cls._number(key, True)
        raise TypeError(f"keys must be str, int, float, bool or None, not {type(key).__name__}")

    @staticmethod
    def _number(value, allow_nan):
        if isinstance(value, int):
            return int.__repr__(value)
        if _math.isfinite(value):
            return float.__repr__(value)
        if not allow_nan:
            raise ValueError("Out of range float values are not JSON compliant")
        if _math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"

    @classmethod
    def dumps(cls, obj, ensure_ascii=True, separators=None, allow_nan=True, **_ignored):
        item_sep, key_sep = separators if separators is not None else (", ", ": ")

        def enc(o):
            if o is None:
                return "null"
            if o is True:
                return "true"
            if o is False:
                return "false"
            if isinstance(o, str):
                return cls._string(o, ensure_ascii)
            if isinstance(o, (int, float)):
                return cls._number(o, allow_nan)
            if isinstance(o, dict):
                return "{" + item_sep.join(cls._string(cls._key(k), ensure_ascii) + key_sep + enc(v)
                                           for k, v in o.items()) + "}"
            if isinstance(o, (list, tuple)):
                return "[" + item_sep.join(enc(v) for v in o) + "]"
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

        return enc(obj)

    @staticmethod
    def loads(text):
        if isinstance(text, (bytes, bytearray)):
            text = text.decode("utf-8")
        pos = [0]
        n = len(text)

        def skip():
            while pos[0] < n and text[pos[0]] in " \t\n\r":
                pos[0] += 1

        def fail(what):
            raise ValueError(f"{what} at position {pos[0]}")

        def string():
            pos[0] += 1                                   # opening quote
            out = []
            while True:
                if pos[0] >= n:
                    fail("Unterminated string")
                ch = text[pos[0]]
                if ch == '"':
                    pos[0] += 1
                    return "".join(out)
                if ch == "\\":
                    esc = text[pos[0] + 1:pos[0] + 2]
                    simple = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
                    if esc in simple:
                        out.append(simple[esc])
                        pos[0] += 2
                    elif esc == "u":
                        code = int(text[pos[0] + 2:pos[0] + 6], 16)
                        pos[0] += 6
                        if 0xD800 <= code <= 0xDBFF and text[pos[0]:pos[0] + 2] == "\\u":
                            low = int(text[pos[0] + 2:pos[0] + 6], 16)
                            if 0xDC00 <= low <= 0xDFFF:
                                code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                                pos[0] += 6
                        out.append(chr(code))
                    else:
                        fail("Invalid escape")
                else:
                    out.append(ch)
                    pos[0] += 1

        def number():
            start = pos[0]
            while pos[0] < n and text[pos[0]] in "+-0123456789.eE":
                pos[0] += 1
            token = text[start:pos[0]]
            if "." in token or "e" in token or "E" in token:
                return float(token)
            return int(token)

        def value():
            skip()
            if pos[0] >= n:
                fail("Expecting value")
            ch = text[pos[0]]
            if ch == "{":
                pos[0] += 1
                obj = {}
                skip()
                if text[pos[0]:pos[0] + 1] == "}":
                    pos[0] += 1
                    return obj
                while True:
                    skip()
                    if text[pos[0]:pos[0] + 1] != '"':
                        fail("Expecting property name")
                    key = string()
                    skip()
                    if text[pos[0]:pos[0] + 1] != ":":
                        fail("Expecting ':'")
                    pos[0] += 1
                    obj[key] = value()
                    skip()
                    sep = text[pos[0]:pos[0] + 1]
                    pos[0] += 1
                    if sep == "}":
                        return obj
                    if sep != ",":
                        fail("Expecting ',' or '}'")
            if ch == "[":
                pos[0] += 1
                arr = []
                skip()
                if text[pos[0]:pos[0] + 1] == "]":
                    pos[0] += 1
                    return arr
                while True:
                    arr.append(value())
                    skip()
                    sep = text[pos[0]:pos[0] + 1]
                    pos[0] += 1
                    if sep == "]":
                        return arr
                    if sep != ",":
                        fail("Expecting ',' or ']'")
            if ch == '"':
                return string()
            for word, result in (("true", True), ("false", False), ("null", None),
                                 ("NaN", float("nan")), ("Infinity", float("inf")), ("-Infinity", float("-inf"))):
                if text.startswith(word, pos[0]):
                    pos[0] += len(word)
                    return result
            return number()

        result = value()
        skip()
        if pos[0] != n:
            fail("Extra data")
        return result


base64 = _Base64Compat
json = _JsonCompat
