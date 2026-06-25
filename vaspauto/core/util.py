import re
import copy
import itertools
from pathlib import Path
from os import PathLike
from typing import Callable, TypeVar

from vaspauto.core.host_info import host


def sub_tilde_home_dir(s: str) -> str:
    """Expand a leading ``~`` to the cluster home directory (Unix semantics)."""
    if s.startswith('~/'):
        return host.home_dir + s[1:]
    elif s == '~':
        return host.home_dir
    return s


def assert_absolute_dir(dir_path: Path) -> None:
    if not dir_path.is_dir():
        raise NotADirectoryError(f'directory {dir_path} not found!')
    if not dir_path.is_absolute():
        raise ValueError(f'directory path {dir_path} must be absolute!')


def assert_duplicate_name(name: str, calc_name_set: set[str]) -> None:
    """
    check for duplicate calculation names
    :param name:
    :param calc_name_set:
    :return:
    """
    if name in calc_name_set:
        raise ValueError(f'duplicate calculation name {name}!')
    calc_name_set.add(name)


# pattern '{VAR}'. for VAR with braces, use backslash (e.g. \{, \})
pattern_braces = re.compile(r'(?<!\\)\{((\\}|[^\\}{])*)}')
_SubType = TypeVar('_SubType')


def str_sub_deep(obj: _SubType, sub_func: str | Callable[[re.Match[str]], str]) -> _SubType:
    """
    do substitution (deep)
    :param obj:
    :param sub_func:
    :return:
    """
    if isinstance(obj, str):
        return re.sub(pattern_braces, sub_func, obj)
    elif isinstance(obj, list):
        return [str_sub_deep(item, sub_func) for item in obj]
    elif isinstance(obj, dict):
        return {key: str_sub_deep(obj[key], sub_func) for key in obj}
    else:
        return copy.deepcopy(obj)


def expand_glob_var(global_vars: dict, root_dir: Path) -> None:
    # expand glob variables (converts {glob="pattern", dir="...", ...} to a list)
    for var_name in global_vars:
        var_value = global_vars[var_name]
        if isinstance(var_value, dict) and 'glob' in var_value:
            glob_pattern = var_value['glob']
            search_dir = root_dir / var_value.get('dir', '.')
            strip_ext = var_value.get('strip_ext', False)

            matches = sorted(search_dir.glob(glob_pattern))
            result: list[str] = []
            for m in matches:
                rel = m.relative_to(search_dir)
                if strip_ext:
                    rel = rel.with_suffix('')
                result.append(str(rel))

            global_vars[var_name] = result


def calc_var_expansion(calc_conf: list[dict], global_vars: dict) -> list[dict]:
    # do substitutions (expand loops)
    calc_name_set: set[str] = set()
    calculations = []
    for calc in calc_conf:
        # find variables to loop for
        var_sub_list = []
        loop_range_list = []
        for g in re.finditer(pattern_braces, calc['name']):
            var_sub = g.group(1)
            if var_sub in global_vars:
                if isinstance(global_vars[var_sub], list):
                    var_sub_list.append(var_sub)
                    loop_range_list.append(range(len(global_vars[var_sub])))
            else:
                raise ValueError(f'variable "{var_sub}" not found!')

        # expand loops
        for idx in itertools.product(*loop_range_list):

            def sub_func(x: re.Match) -> str:
                s = x.group(1)
                if s in global_vars:
                    if isinstance(global_vars[s], list):
                        if s in var_sub_list:
                            i = var_sub_list.index(s)
                            return global_vars[s][idx[i]]
                        else:
                            raise ValueError(f'cannot find the index of variable "{s}" when expanding loops! '
                                             f'you can append ":" and a variable in the calculation name '
                                             f'to assign the index of variable "{s}".')
                    else:
                        return global_vars[s]
                elif ':' in s:
                    var1, var2 = s.split(':', maxsplit=1)
                    if var1 not in global_vars:
                        raise ValueError(f'variable "{var1}" not found!')
                    if not isinstance(global_vars[var1], list):
                        raise ValueError(f'variable "{var1}" must be a list!')
                    # support for n-dimensional array
                    var2_list = var2.split(',')
                    res = global_vars[var1]
                    for var3 in var2_list:
                        try:
                            # var3 is a integer
                            i = int(var3)
                            res = res[i]
                        except ValueError:
                            # var3 is a variable
                            if var3 not in var_sub_list:
                                raise ValueError(f'variable "{var3}" must be in calculation name!')
                            i = var_sub_list.index(var3)
                            res = res[idx[i]]
                    return res
                else:
                    raise ValueError(f'substitution variable "{s}" not found!')

            calc_expanded = str_sub_deep(calc, sub_func)
            assert_duplicate_name(calc_expanded['name'], calc_name_set)
            if 'dependence' not in calc_expanded:
                calc_expanded['dependence'] = []
            calculations.append(calc_expanded)
    return calculations


def read_last_line(fname: PathLike) -> str:
    fin = open(fname, 'rb')
    try:
        fin.seek(-1, 2)
    except OSError:
        # empty file
        return ''
    pos = fin.tell()
    # skip last \n if last character is \n
    if fin.read(1) == b'\n':
        pos -= 1
    # find \n
    while pos >= 0:
        fin.seek(pos)
        if fin.read(1) == b'\n' and pos != 0:
            break
        pos -= 1
    last_line = fin.readline().decode()
    fin.close()
    return last_line


pattern_energy = re.compile(r' *[0-9]+ F= ([+\-.Ee0-9]+)')


def get_energy_str_oszicar(oszicar) -> str | None:
    ener_str: str | None = None
    with open(oszicar, 'r') as fin:
        for line in fin:
            m = re.match(pattern_energy, line)
            if m is not None:
                ener_str = m.group(1)
    return ener_str
