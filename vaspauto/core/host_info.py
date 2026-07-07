"""
Cluster host information loaded from ~/.config/vaspauto/host.toml.

Detection order:
  1. $VASPAUTO_HOSTS_FILE  -> load config from that exact path
     (set by submit.py in generated Slurm scripts; compute nodes
      use this to avoid hostname-based detection entirely.)
  2. ~/.config/vaspauto/host.toml -> load host configuration.
  3. Auto-detect via Slurm commands (sinfo / lscpu) and write a new
     config to ~/.config/vaspauto/host.toml automatically.

See host.example.toml for the configuration format.
"""
import os
import socket
import pathlib
import subprocess
import sys
from typing import Optional

import tomli_w
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _ensure_nl(s: str) -> str:
    """Return *s* with exactly one trailing newline (if non-empty)."""
    if not s:
        return s
    return s.rstrip('\n') + '\n'


def _run(cmd: list[str], timeout: float = 5) -> str:
    """Run a command, return stripped stdout, or empty string on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ''
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ''


def _auto_detect() -> dict:
    """Auto-detect cluster configuration via Slurm / Linux commands.

    Returns a dictionary that can be written directly as a host.toml config.
    The user is expected to fill in ``paths`` and ``modules``.
    """
    hostname = socket.gethostname()
    home_dir = os.environ.get('HOME', f'/home/{os.environ.get("USER", "unknown")}')

    # --- Detect partitions via sinfo ---
    sinfo_out = _run(['sinfo', '-o', '%P|%c|%O|%D', '--noheader'])

    partitions: dict[str, dict] = {}
    seen: set[str] = set()
    default_partition = ''

    if sinfo_out:
        for line in sinfo_out.splitlines():
            parts = line.strip().split('|')
            if len(parts) < 2:
                continue
            raw_name = parts[0].strip()
            # sinfo appends '*' to the default partition
            pname = raw_name.rstrip('*')
            if not pname or pname in seen:
                continue
            seen.add(pname)

            try:
                logical = int(parts[1].strip())
            except ValueError:
                continue

            # Try physical CPU count from sinfo
            phys = logical
            if len(parts) >= 3 and parts[2].strip():
                try:
                    phys = int(parts[2].strip())
                except ValueError:
                    pass

            partitions[pname] = {
                'cpus_per_node': logical,
                'phys_cpus_per_node': phys,
            }

            if raw_name.endswith('*'):
                default_partition = pname

        # If no default was marked, use the first partition
        if not default_partition and partitions:
            default_partition = next(iter(partitions))

    # --- Fallback: lscpu or os.cpu_count() ---
    if not partitions:
        lscpu_out = _run(['lscpu'])
        logical = 0
        phys = 0
        sockets = 1
        cores_per_socket = 0
        for line in lscpu_out.splitlines():
            if line.startswith('CPU(s):') and 'On-line' not in line and 'List' not in line:
                try:
                    logical = int(line.split(':')[1].strip())
                except (ValueError, IndexError):
                    pass
            if 'Core(s) per socket' in line:
                try:
                    cores_per_socket = int(line.split(':')[1].strip())
                except (ValueError, IndexError):
                    pass
            if 'Socket(s)' in line and not line.startswith('Thread'):
                try:
                    sockets = int(line.split(':')[1].strip())
                except (ValueError, IndexError):
                    pass
        if cores_per_socket and sockets:
            phys = cores_per_socket * sockets
        if logical == 0:
            logical = os.cpu_count() or 1
        if phys == 0:
            phys = logical

        pname = 'default'
        partitions[pname] = {
            'cpus_per_node': logical,
            'phys_cpus_per_node': phys,
        }
        default_partition = pname

    # --- Build config ---
    name = hostname.split('.')[0]

    # Modules: use echo-and-exit stubs that the user must replace.
    stub = "echo 'error: please configure this module in ~/.config/vaspauto/host.toml' && exit 1"

    config = {
        'name': name,
        'default_partition': default_partition,
        'home_dir': home_dir,
        'partitions': dict(sorted(partitions.items())),
        'paths': {
            'vasp_pot_pbe': '$HOME/path/to/POT_PBE',
            'vasp_pot_lda': '$HOME/path/to/POT_LDA',
            'cp2k_data': '$HOME/path/to/cp2k_data',
        },
        'modules': {
            'common': 'HOME={home_dir}\nmodule purge',
            'vasp': stub,
            'cp2k': stub,
            'python': stub,
        },
    }
    return config


def _write_config(config: dict, path: pathlib.Path) -> None:
    """Write ``config`` to *path* as readable TOML, with leading comments."""
    header = (
        f'# Auto-generated by vaspauto on {socket.gethostname()}\n'
        f'# Please review and edit the sections below before running calculations.\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as f:
        # Write header + config; tomli_w handles the rest
        f.write(header.encode('ascii'))
        tomli_w.dump(config, f, multiline_strings=True)



class HostInfo:
    def __init__(self, config_path: Optional[str] = None):
        self.hostname = socket.gethostname()
        if config_path:
            self.config_path = pathlib.Path(config_path)
        else:
            self.config_path = self._find_config()
        self.config = self._load_config(self.config_path)
        self._apply()

    # ------------------------------------------------------------------
    #  Config file discovery
    # ------------------------------------------------------------------

    def _find_config(self) -> pathlib.Path:
        """Locate the host configuration file."""
        # 1. $VASPAUTO_HOSTS_FILE  (set by submit.py in Slurm scripts)
        env_path = os.environ.get('VASPAUTO_HOSTS_FILE')
        if env_path:
            p = pathlib.Path(env_path)
            if p.is_file():
                return p
            raise FileNotFoundError(
                f'$VASPAUTO_HOSTS_FILE={env_path}  does not exist')

        # 2. Default user location
        default = (pathlib.Path.home()
                   / '.config' / 'vaspauto' / 'host.toml')
        if default.is_file():
            return default

        # 3. Auto-detect and write a new config
        print('No host configuration found. Auto-detecting cluster settings...')
        config = _auto_detect()
        _write_config(config, default)
        print(f'Auto-generated config written to: {default}')
        print('Please review and edit the following sections manually:')
        print('  - paths          : correct the VASP pseudopotential and CP2K data paths')
        print('  - modules        : configure the module load commands for vasp/cp2k/python')
        print('    (placeholder error commands have been inserted as defaults)')
        return default

    @staticmethod
    def _load_config(path: pathlib.Path) -> dict:
        with open(path, 'rb') as f:
            return tomllib.load(f)

    # ------------------------------------------------------------------
    #  Apply configuration
    # ------------------------------------------------------------------

    def _apply(self):
        cfg = self.config

        # -- validate required top-level fields --
        for key in ['name', 'default_partition', 'home_dir', 'paths',
                     'modules', 'partitions']:
            if key not in cfg:
                raise KeyError(f'{self.config_path}: missing required '
                               f'field "{key}"')

        # -- basic attributes --
        self.name = cfg['name']
        self.host = self.name                     # backward-compat alias
        self.default_partition = cfg['default_partition']
        self.partition = self.default_partition
        self.home_dir = cfg['home_dir']

        # -- partitions (required) --
        self._partitions = cfg['partitions']

        # read CPU counts from default partition
        default_part = self._partitions[self.default_partition]
        self.cpus_per_node = default_part['cpus_per_node']
        self.phys_cpus_per_node = default_part['phys_cpus_per_node']

        # -- paths: expand $HOME -> home_dir --
        paths = cfg['paths']
        _x = lambda s: s.replace('$HOME', self.home_dir)
        self.vasp_pot_dir_pbe = _x(paths.get('vasp_pot_pbe', ''))
        self.vasp_pot_dir_lda = _x(paths.get('vasp_pot_lda', ''))
        self.cp2k_data_dir = _x(paths.get('cp2k_data', ''))

        # -- module commands: expand {home_dir} -> home_dir --
        mods = cfg['modules']
        _m = lambda s: s.replace('{home_dir}', self.home_dir)
        self._mod_common = _m(_ensure_nl(mods.get('common', '')))
        self._mod_vasp   = _m(_ensure_nl(mods.get('vasp', '')))
        self._mod_cp2k   = _m(_ensure_nl(mods.get('cp2k', '')))
        self._mod_py     = _m(_ensure_nl(mods.get('python', '')))

    # ------------------------------------------------------------------
    #  Partition switching
    # ------------------------------------------------------------------

    def use_partition(self, partition: str):
        """Switch to *partition* and update CPU counts accordingly."""
        self.partition = partition
        part_cfg = self._partitions.get(partition)
        if part_cfg:
            if 'cpus_per_node' in part_cfg:
                self.cpus_per_node = part_cfg['cpus_per_node']
            if 'phys_cpus_per_node' in part_cfg:
                self.phys_cpus_per_node = part_cfg['phys_cpus_per_node']

    # ------------------------------------------------------------------
    #  Module strings (used by task_submit.py to build Slurm scripts)
    # ------------------------------------------------------------------

    @property
    def environment_common_str(self) -> str:
        return self._mod_common

    @property
    def environment_vasp_str(self) -> str:
        return self._mod_vasp

    @property
    def environment_cp2k_str(self) -> str:
        return self._mod_cp2k

    @property
    def environment_py_str(self) -> str:
        return self._mod_py


# Module-level singleton -- created at import time.
try:
    host = HostInfo()
except (FileNotFoundError, KeyError, ValueError) as e:
    print(f'Error loading host config: {e}', file=sys.stderr)
    print('Please configure ~/.config/vaspauto/host.toml manually.', file=sys.stderr)
    sys.exit(1)
