import numpy as np
from dataclasses import dataclass, field


@dataclass
class Poscar:
    formula = ''
    lattice_vector: np.ndarray = field(default_factory=lambda: np.empty(0))
    scale = 1.0
    elements: list[str] = field(default_factory=list)
    elements_num: list[int] = field(default_factory=list)
    N_atom = 0
    atoms: np.ndarray = field(default_factory=lambda: np.empty(0))
    coord_type = ''

    @classmethod
    def from_file(cls, file_path):
        self = cls()
        self.lattice_vector = np.zeros([3, 3])
        with open(file_path, 'r') as fin:
            self.formula = fin.readline().strip()
            self.scale = float(fin.readline().strip())
            for ilat in range(3):
                nums = fin.readline().strip().split()
                for iaxis in range(3):
                    self.lattice_vector[ilat, iaxis] = float(nums[iaxis])
            # TODO: according to VASP wiki, the following line is optional (read from POTCAR if not present)
            self.elements = fin.readline().strip().split()
            self.elements_num = [int(num_str) for num_str in fin.readline().strip().split()]
            self.element_type = [self.elements[i] for i in range(len(self.elements))
                                 for _ in range(self.elements_num[i])]
            self.N_atom = sum(self.elements_num)
            self.coord_type = fin.readline().strip()
            self.atoms = np.zeros([self.N_atom, 3])
            for iatom in range(self.N_atom):
                nums = fin.readline().strip().split()
                for iaxis in range(3):
                    self.atoms[iatom, iaxis] = float(nums[iaxis])
        return self

    def write_file(self, file_path):
        with open(file_path, 'w') as fout:
            fout.write(f'{self.formula}\n')
            fout.write(f'{self.scale}\n')
            fout.write(f'{self.lattice_vector[0, 0]} {self.lattice_vector[0, 1]} {self.lattice_vector[0, 2]}\n')
            fout.write(f'{self.lattice_vector[1, 0]} {self.lattice_vector[1, 1]} {self.lattice_vector[1, 2]}\n')
            fout.write(f'{self.lattice_vector[2, 0]} {self.lattice_vector[2, 1]} {self.lattice_vector[2, 2]}\n')

            for i in range(len(self.elements)):
                fout.write(f' {self.elements[i]}')
            fout.write('\n')
            for i in range(len(self.elements)):
                fout.write(f' {self.elements_num[i]}')
            fout.write('\n')
            fout.write(f'{self.coord_type}\n')
            for i in range(self.N_atom):
                fout.write(f'{self.atoms[i, 0]} {self.atoms[i, 1]} {self.atoms[i, 2]}\n')

    def coord_is_cartesian(self) -> bool:
        return self.coord_type[0].lower() in 'ck'

    def coord_is_direct(self) -> bool:
        return not self.coord_is_cartesian()

    def to_cartesian(self):
        if self.coord_is_direct():
            self.atoms = self.atoms @ self.lattice_vector
            self.coord_type = 'Cartesian'

    def to_direct(self):
        if self.coord_is_cartesian():
            self.atoms = self.atoms @ np.linalg.inv(self.lattice_vector)
            self.coord_type = 'Direct'

    def warp_coord(self):
        if self.coord_is_cartesian():
            self.to_direct()
        self.atoms = np.fmod(self.atoms, 1.0)
        self.atoms = np.where(self.atoms < 0.0, self.atoms + 1, self.atoms)
