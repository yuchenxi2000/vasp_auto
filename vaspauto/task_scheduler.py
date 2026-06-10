# -*- coding: UTF-8 -*-
"""
Task scheduler: reads the TOML config, expands variable loops, resolves
dependencies (topological sort), and dispatches calculations via calc_runner.

File locks allow multiple Slurm jobs to share one config file safely.
"""
import copy
import itertools
import pathlib
import re
import argparse
import warnings
import filelock
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from vaspauto.host_info import host
from vaspauto import calc_runner

# parse arguments
parser = argparse.ArgumentParser(description='automatic python script for vasp calculation, author: YCX',
                                 prog='VaspAuto')
parser.add_argument('-v', '--version', action='version', version='%(prog)s 5.1')
parser.add_argument('-c', '--config', dest='config', help='config file')
parser.add_argument('-d', '--dir', dest='dir', help='calculation root dir')
parser.add_argument('--print-num-groups', dest='print_num_groups', action='store_true',
                    help='print number of independent groups')
parser.add_argument('--write-expanded-config', dest='write_expanded_config',
                    help='write variable expanded config file for debug. requires tomli_w package')
parser.add_argument('--print-groups', dest='print_groups', action='store_true', help='print calculation groups')
parser.add_argument('-n', dest='num_tasks', type=int, required=True, help='total tasks')
parser.add_argument('--nc', dest='cpus_per_task', type=int, default=1, help='number of cpus per task')
parser.add_argument('--rm-locks', dest='rm_locks', action='store_true',
                    help='remove all lock files. these files should be removed before next submission '
                         'if task is cancelled mannually.')
args = parser.parse_args()

# read & parse config file
if args.config:
    config_file = pathlib.Path(args.config)
else:
    config_file = pathlib.Path('config.toml')
config = tomllib.load(config_file.open('rb'))

# check version
if 'version' not in config:
    raise Exception('version 1.x is not supported!')
else:
    major_version = int(config['version'].split('.')[0])
    if major_version < 5:
        warnings.warn(f'version {major_version}.x is not supported!')


def check_absolute_dir(dir_path: pathlib.Path):
    if not dir_path.is_dir():
        raise NotADirectoryError(f'directory {dir_path} not found!')
    if not dir_path.is_absolute():
        raise ValueError(f'directory path {dir_path} must be absolute!')


# parallel params
num_tasks = args.num_tasks
cpus_per_task = args.cpus_per_task
use_omp = cpus_per_task > 1

pattern_tilde = re.compile(r'\\\\|~|\\~')


def sub_func_tilde(g: re.Match) -> str:
    match_str = g.group(0)
    if match_str == '\\\\':
        return '\\'
    elif match_str == '\\~':
        return '\\~'
    elif match_str == '~':
        return host.home_dir
    else:
        return ''


# root dir
if 'root_dir' in config['global']:
    dir_str = config['global']['root_dir']
    dir_str_expanded = re.sub(pattern_tilde, sub_func_tilde, dir_str)
    root_dir = pathlib.Path(dir_str_expanded)
elif args.dir is not None:
    root_dir = pathlib.Path(args.dir)
else:
    root_dir = pathlib.Path('.')
check_absolute_dir(root_dir)

# variables
if 'vars' in config['global']:
    global_vars = config['global']['vars']
else:
    global_vars = {}

# expand glob variables (converts {glob="pattern", dir="...", ...} to a list)
for var_name, var_value in list(global_vars.items()):
    if isinstance(var_value, dict) and 'glob' in var_value:
        glob_pattern = var_value['glob']
        search_dir = root_dir / var_value.get('dir', '.')
        strip_ext = var_value.get('strip_ext', False)

        matches = sorted(search_dir.glob(glob_pattern))
        result = []
        for m in matches:
            rel = m.relative_to(search_dir)
            if strip_ext:
                rel = rel.with_suffix('')
            result.append(str(rel))

        global_vars[var_name] = result

# pattern '{VAR}'. for VAR with braces, use backslash (e.g. \{, \})
pattern_braces = re.compile(r'(?<!\\)\{((\\}|[^\\}{])*)}')
calc_name_set = set()


def sub(obj, sub_func):
    """
    do substitution (deep)
    :param obj:
    :param sub_func:
    :return:
    """
    if isinstance(obj, str):
        return re.sub(pattern_braces, sub_func, obj)
    elif isinstance(obj, list):
        return [sub(item, sub_func) for item in obj]
    elif isinstance(obj, dict):
        return {key: sub(obj[key], sub_func) for key in obj}
    else:
        return copy.deepcopy(obj)


def check_duplicate_name(name):
    """
    check for duplicate calculation names
    :param name:
    :return:
    """
    if name in calc_name_set:
        raise ValueError(f'duplicate calculation name {name}!')
    calc_name_set.add(name)


# do substitutions (expand loops)
calculations = []
for calc in config['calculation']:
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

        def sub_func(x: re.Match):
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

        calc_expanded = sub(calc, sub_func)
        check_duplicate_name(calc_expanded['name'])
        if 'dependence' not in calc_expanded:
            calc_expanded['dependence'] = []
        calculations.append(calc_expanded)


if args.write_expanded_config:
    config['calculation'] = calculations
    try:
        import tomli_w
    except ImportError:
        sys.exit('tomli_w is required for --write-expanded-config. '
                 'Install it with: pip install tomli_w')
    tomli_w.dump(config, open(args.write_expanded_config, 'wb'))
    exit()


def get_rank(graph: list[dict], idx: int, visited: list[bool]) -> int:
    """
    get the rank of node in graph.
    rank is defined to be maximum rank of dependent nodes plus one.
    :param graph:
    :param idx:
    :param visited:
    :return:
    """
    if visited[idx]:
        raise ValueError('this graph has loop(s)!')
    else:
        visited[idx] = True
    if len(graph[idx]['_dep']) == 0:
        graph[idx]['_rank'] = 0
        return 0
    elif '_rank' in graph[idx]:
        return graph[idx]['_rank']
    else:
        max_rank = 0
        for dep in graph[idx]['_dep']:
            rank = get_rank(graph, dep, visited)
            if max_rank < rank:
                max_rank = rank
        graph[idx]['_rank'] = max_rank + 1
        return max_rank + 1


def rank(graph: list[dict]):
    for i in range(len(graph)):
        get_rank(graph, i, [False] * len(graph))


def dep2idx(graph: list[dict]) -> None:
    """
    add _dep property, which stores index of dependencies in the list
    :param graph:
    :return:
    """
    for i, node1 in enumerate(graph):
        node1['_dep'] = []
        for dep in node1['dependence']:
            dep_found = False
            for j, node2 in enumerate(graph):
                if dep == node2['name']:
                    node1['_dep'].append(j)
                    dep_found = True
                    break
            if not dep_found:
                raise ValueError(f'dependence \'{dep}\' of \'{node1["name"]}\' not found!')


def get_neighbors(graph: list[dict]):
    """
    get set of neighboring nodes
    :param graph:
    :return:
    """
    for node in graph:
        if '_neighbor' in node:
            del node['_neighbor']
    for i, node1 in enumerate(graph):
        if '_neighbor' in node1:
            node1['_neighbor'] = node1['_neighbor'].union(node1['_dep'])
        else:
            node1['_neighbor'] = set(node1['_dep'])
        for dep in node1['_dep']:
            node2: dict = graph[dep]
            if '_neighbor' in node2:
                node2['_neighbor'].add(i)
            else:
                node2['_neighbor'] = {i}


def get_connected_subgraph(graph: list[dict], node_idx: int, group_idx: int):
    if '_group' in graph[node_idx]:
        return
    else:
        graph[node_idx]['_group'] = group_idx
        for neighbor in graph[node_idx]['_neighbor']:
            get_connected_subgraph(graph, neighbor, group_idx)


def group(graph: list[dict]) -> int:
    """
    divide into connected sub-graphs
    :param graph:
    :return: number of sub-graphs
    """
    group_idx = 0
    for node_idx, node in enumerate(graph):
        if '_group' not in node:
            get_connected_subgraph(graph, node_idx, group_idx)
            group_idx += 1
    return group_idx


def get_nodep_groups(calculations: list[dict]) -> list[list[dict]]:
    """
    divide into groups that are independent to each other
    :param calculations: list of calculation configurations
    :return: calculation groups
    """
    dep2idx(calculations)
    get_neighbors(calculations)
    group_num = group(calculations)
    calculation_groups: list[list[dict]] = [[] for i in range(group_num)]
    for calc in calculations:
        group_idx = calc['_group']
        calculation_groups[group_idx].append(calc)
    return calculation_groups


calculation_groups = get_nodep_groups(calculations)

if args.print_num_groups:
    print(f'number of independent groups: {len(calculation_groups)}')
    exit()

# sort within each group
for calculation_group in calculation_groups:
    dep2idx(calculation_group)
    get_neighbors(calculation_group)
    rank(calculation_group)
    calculation_group.sort(key=lambda x: x['_rank'])

if args.print_groups:
    for i, calc_group in enumerate(calculation_groups):
        print(f'group {i}:')
        for calc in calc_group:
            print(f"    name: {calc['name']}, dependence: {calc['dependence']}")
        print()
    exit()

if args.rm_locks:
    for calc_group in calculation_groups:
        for calc in calc_group:
            lock_file = root_dir.joinpath(calc['calc_dir']).joinpath('.lock')
            if lock_file.is_file():
                lock_file.unlink()
    exit()

# start calculation
for i, calc_group in enumerate(calculation_groups):
    for calc in calc_group:
        calc_obj = calc_runner.get_calculation(calc, root_dir)
        try:
            with calc_obj.lock:
                if calc_obj.status == calc_runner.CalcStatus.FINISHED:
                    print(f'skip finished task: {calc["name"]}', flush=True)
                    calc['_status'] = calc_runner.CalcStatus.FINISHED
                    continue
                # stop if dependence is not finished
                dep_all_finished = True
                for dep_idx in calc['_dep']:
                    calc_dep = calc_group[dep_idx]
                    if calc_dep['_status'] != calc_runner.CalcStatus.FINISHED:
                        print(f'calculation {calc["name"]} stopped, because dependence {calc_dep["name"]} is not finished!', flush=True)
                        calc['_status'] = calc_runner.CalcStatus.NOT_CALCULATED
                        dep_all_finished = False
                        continue
                if not dep_all_finished:
                    continue
                # start calculation
                calc_obj.run(num_tasks, cpus_per_task)
                calc['_status'] = calc_obj.status
        except filelock.Timeout:
            print(f'skip calculation group {i}, because another process is working on calculation {calc["name"]}', flush=True)
            break
