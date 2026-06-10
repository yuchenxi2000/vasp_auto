"""
Cluster host information loaded from ~/.config/vaspauto/host.toml.

Detection order:
  1. $VASPAUTO_HOSTS_FILE  → load config from that exact path
     (set by task_submit.py in generated Slurm scripts; compute nodes
      use this to avoid hostname-based detection entirely.)
  2. ~/.config/vaspauto/host.toml → load and verify hostname against
     the optional ``match`` field.

See host.example.toml for the configuration format.
"""
import os
import socket
import fnmatch
import pathlib
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _ensure_nl(s: str) -> str:
    """Return *s* with exactly one trailing newline (if non-empty)."""
    if not s:
        return s
    return s.rstrip('\n') + '\n'


class HostInfo:
    def __init__(self, config_path = None):  # type: (os.PathLike | None) -> None
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
        # 1. $VASPAUTO_HOSTS_FILE  (set by task_submit.py in Slurm scripts)
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

        raise FileNotFoundError(
            'Host configuration not found.\n'
            'Create  ~/.config/vaspauto/host.toml  based on host.example.toml'
        )

    @staticmethod
    def _load_config(path: pathlib.Path) -> dict:
        with open(path, 'rb') as f:
            return tomllib.load(f)

    # ------------------------------------------------------------------
    #  Apply configuration
    # ------------------------------------------------------------------

    def _apply(self):
        cfg = self.config
        via_env = 'VASPAUTO_HOSTS_FILE' in os.environ

        # -- validate required top-level fields --
        for key in ['name', 'default_partition', 'home_dir', 'paths',
                     'modules', 'partitions']:
            if key not in cfg:
                raise KeyError(f'{self.config_path}: missing required '
                               f'field "{key}"')

        # -- hostname verification --
        # skip when loaded via $VASPAUTO_HOSTS_FILE (trust the submit node)
        if not via_env and 'match' in cfg:
            if not any(fnmatch.fnmatch(self.hostname, p)
                       for p in cfg['match']):
                raise ValueError(
                    f'hostname "{self.hostname}" does not match any '
                    f'pattern in {self.config_path} "match": {cfg["match"]}'
                )

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

        # -- paths: expand $HOME → home_dir --
        paths = cfg['paths']
        _x = lambda s: s.replace('$HOME', self.home_dir)
        self.vasp_pot_dir_pbe = _x(paths.get('vasp_pot_pbe', ''))
        self.vasp_pot_dir_lda = _x(paths.get('vasp_pot_lda', ''))
        self.cp2k_data_dir = _x(paths.get('cp2k_data', ''))

        # -- module commands: expand {home_dir} → home_dir --
        # also ensure each block ends with a newline so concatenation is safe.
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


# Module-level singleton — created at import time.
host = HostInfo()
