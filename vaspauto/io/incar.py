"""
INCAR file parser supporting VASP 6 nested tags.

VASP 6 added tags with a tree structure, e.g.:
    KERNEL_TRUNCATION {
        LTRUNCATE      = T
        IDIMENSIONALITY = 0
        LCOARSEN       = T
    }

These are stored internally as flat keys with '/' as path separator:
    kvs["KERNEL_TRUNCATION/LTRUNCATE"] = ["T"]
    kvs["KERNEL_TRUNCATION/IDIMENSIONALITY"] = ["0"]
    kvs["KERNEL_TRUNCATION/LCOARSEN"] = ["T"]

The get/set/del_key API works naturally with these path-based keys.

References:
    https://vasp.at/wiki/KERNEL_TRUNCATION/IDIMENSIONALITY
    https://vasp.at/wiki/INCAR
"""
import dataclasses
import re
from collections.abc import Generator
from typing import Optional


@dataclasses.dataclass
class Incar:
    kvs: dict = dataclasses.field(default_factory=dict)

    # ------------------------------------------------------------------
    #  Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _insert_into(result: dict, key: str, value):
        """Insert (key, value) into a result dict with list semantics."""
        if key in result:
            result[key].append(str(value))
        else:
            result[key] = [str(value)]

    def insert(self, key: str, value):
        """Insert a key-value pair (public API, appends for duplicates)."""
        self._insert_into(self.kvs, key, value)

    def _parse_lines(self, lines: list[str], start_idx: int, prefix: str
                     ) -> tuple[int, dict]:
        """
        Parse lines from start_idx until a '}' line or EOF.

        Returns (next_line_index, {key: [values]}).
        All keys are prefixed with *prefix* (used for nested blocks).

        Handles these patterns (in priority order):
          1. empty / comment-only lines       → skip
          2. '}' anywhere on the line          → end block (parse any
             (possibly with KEY=VALUE before it)    KEY=VALUE before the brace)
          3. 'KEY {'                           → nested block (recurse;
             (possibly with content after {)         content after { is
                                                    parsed as first child line)
          4. 'KEY = "value"'                   → quoted value (multi-line ok)
          5. 'KEY = value'                     → plain value
        """
        result: dict = {}
        i = start_idx

        while i < len(lines):
            line = lines[i]

            # ---- 1. blank line or comment-only line ----
            if (not line.strip()
                    or re.fullmatch(r' *[#!].*', line)):
                i += 1
                continue

            # ---- 2. closing brace — may appear alone or after a value ----
            if '}' in line:
                # split at the first '}' — anything before it is content
                before, after = line.split('}', 1)
                before = before.strip()
                if before and '=' in before:
                    # parse "KEY = VALUE" before the brace
                    m = re.fullmatch(r' *([^= ]+) *= *([^#!]+).*', before)
                    if m:
                        self._insert_into(result, prefix + m.group(1),
                                         m.group(2).strip())
                return i + 1, result

            # ---- 3. nested block opener:  KEY {  [content-after-brace] ----
            m = re.fullmatch(r' *(\S+)\s*\{(.*)', line)
            if m:
                section_name = m.group(1)
                after_brace = m.group(2).strip()
                child_prefix = f'{prefix}{section_name}/'

                # content after '{' on the same line → replace current
                # line with it and recurse from *this* index (not i+1).
                # if there is no after-brace content, skip this line and
                # recurse from i+1.
                if after_brace:
                    lines[i] = after_brace       # safe: parent already
                    i, child_kvs = self._parse_lines(   # consumed this line
                        lines, i, child_prefix)
                else:
                    i, child_kvs = self._parse_lines(
                        lines, i + 1, child_prefix)

                for k, v in child_kvs.items():
                    if k in result:
                        result[k].extend(v)
                    else:
                        result[k] = list(v)
                continue

            # ---- 4. quoted value (possibly multi-line):  KEY = "... ----
            m = re.fullmatch(r' *([^= ]+) *= *"(.*)', line)
            if m is not None:
                key = prefix + m.group(1)
                value = m.group(2) + '\n'
                right_quote_found = False
                i += 1
                while i < len(lines):
                    res = lines[i].split('"', maxsplit=1)
                    if len(res) == 1:
                        value += res[0] + '\n'
                        i += 1
                    else:
                        value += res[0]
                        right_quote_found = True
                        i += 1
                        break
                if not right_quote_found:
                    raise SyntaxError('quote not enclosed!')
                self._insert_into(result, key, value)
                continue

            # ---- 5. plain value:  KEY = value  [optional comment] ----
            m = re.fullmatch(r' *([^= ]+) *= *([^#!]+).*', line)
            if m is not None:
                key = prefix + m.group(1)
                value = m.group(2).strip()
                self._insert_into(result, key, value)
                i += 1
                continue

            # unrecognised line → skip
            i += 1

        return i, result

    def parse_str(self, s: str):
        """Parse an INCAR string into self.kvs."""
        s = s.replace(';', '\n')          # ; is a line separator
        s = re.sub(r'\\ *\n', '', s)      # \<spaces>\n  → continuation
        lines = s.split('\n')
        _, parsed = self._parse_lines(lines, 0, '')
        self.kvs = parsed

    # ------------------------------------------------------------------
    #  Accessors
    # ------------------------------------------------------------------

    def del_key(self, key: str):
        if key in self.kvs:
            del self.kvs[key]

    def set(self, key: str, value):
        self.kvs[key] = [str(value)]

    def get(self, key: str) -> Optional[str]:
        """Return the first value for *key*, or None.

        VASP allows duplicate INCAR tags but only the *first* occurrence
        takes effect.  This method therefore returns the first stored value.
        """
        if key in self.kvs:
            value_list = self.kvs[key]
            if len(value_list) >= 1:
                return value_list[0]
        return None

    # ------------------------------------------------------------------
    #  Serialisation
    # ------------------------------------------------------------------

    def _emit_block(self, kvs: dict, indent: int = 0
                    ) -> Generator[str, None, None]:
        """
        Recursively emit lines for a block of key-value pairs.

        Flat keys (no '/') are emitted as ``KEY = VALUE``.
        Keys containing '/' are grouped by their first path component
        and emitted as nested ``SECTION { ... }`` blocks.
        """
        tab = '    ' * indent
        flat: dict = {}       # key -> [values]
        sections: dict = {}   # section_name -> {sub_key: [values]}

        for key, values in kvs.items():
            if '/' in key:
                section, rest = key.split('/', 1)
                if section not in sections:
                    sections[section] = {}
                if rest in sections[section]:
                    sections[section][rest].extend(values)
                else:
                    sections[section][rest] = list(values)
            else:
                flat[key] = values

        # emit flat keys
        for key in flat:
            for v in flat[key]:
                yield f'{tab}{key} = {v}'

        # emit nested sections
        for sec, sub_kvs in sections.items():
            yield f'{tab}{sec} {{'
            yield from self._emit_block(sub_kvs, indent + 1)
            yield f'{tab}}}'

    def iter_lines(self) -> Generator[str, None, None]:
        yield from self._emit_block(self.kvs)

    def to_str(self) -> str:
        s = ''
        for line in self.iter_lines():
            s += line + '\n'
        return s

    # ------------------------------------------------------------------
    #  File I/O
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, filepath) -> 'Incar':
        obj = cls()
        with open(filepath, 'r') as fin:
            s = fin.read()
        obj.parse_str(s)
        return obj

    @classmethod
    def from_str(cls, s: str) -> 'Incar':
        obj = cls()
        obj.parse_str(s)
        return obj

    def write_file(self, filepath):
        with open(filepath, 'w') as fout:
            for line in self.iter_lines():
                fout.write(line + '\n')

    def __str__(self):
        return self.to_str()
