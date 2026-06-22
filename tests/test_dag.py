from vaspauto.core.task import Task
from pathlib import Path


def test_case1():
    task_obj = Task.from_config_file(Path(__file__).parent / 'config_files' / 'config1.toml')
    ranks = [{
        'calc7': 0, 'calc8': 1
    }, {
        'calc1': 0, 'calc2': 0, 'calc3': 1, 'calc4': 2, 'calc5': 2, 'calc6': 3,
    }]
    for icomp, comp in enumerate(task_obj.calc_comps):
        for calc in comp:
            assert calc.rank == ranks[icomp][calc.name]


if __name__ == '__main__':
    test_case1()
