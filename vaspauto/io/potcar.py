"""
Only VASP 5.4 pseudopotentials supported
"""
from vaspauto.core.host_info import host
import subprocess
import argparse

pot_pbe = host.vasp_pot_dir_pbe
pot_lda = host.vasp_pot_dir_lda

# https://www.vasp.at/wiki/index.php/Choosing_pseudopotentials
# we only record the potentials of different name with elements
recommended_pot_for_elem_except = {
    'Li': 'Li_sv', 'Na': 'Na_pv', 'K': 'K_sv', 'Ca': 'Ca_sv', 'Sc': 'Sc_sv', 'Ti': 'Ti_sv', 'V': 'V_sv', 'Cr': 'Cr_pv',
    'Mn': 'Mn_pv', 'Ga': 'Ga_d', 'Ge': 'Ge_d', 'Rb': 'Rb_sv', 'Sr': 'Sr_sv', 'Y': 'Y_sv', 'Zr': 'Zr_sv', 'Nb': 'Nb_sv',
    'Mo': 'Mo_sv', 'Tc': 'Tc_pv', 'Ru': 'Ru_pv', 'Rh': 'Rh_pv', 'In': 'In_d', 'Sn': 'Sn_d', 'Cs': 'Cs_sv',
    'Ba': 'Ba_sv', 'Pr': 'Pr_3', 'Nd': 'Nd_3', 'Pm': 'Pm_3', 'Sm': 'Sm_3', 'Eu': 'Eu_2', 'Gd': 'Gd_3', 'Tb': 'Tb_3',
    'Dy': 'Dy_3', 'Ho': 'Ho_3', 'Er': 'Er_3', 'Tm': 'Tm_3', 'Yb': 'Yb_2', 'Lu': 'Lu_3', 'Hf': 'Hf_pv', 'Ta': 'Ta_pv',
    'W': 'W_sv', 'Tl': 'Tl_d', 'Pb': 'Pb_d', 'Bi': 'Bi_d', 'Po': 'Po_d', 'Fr': 'Fr_sv', 'Ra': 'Ra_sv',
}


class Potcar:
    def __init__(self, pot_list: list, pot_type: str):
        self.pot_type = pot_type
        self.pot_list = pot_list

    @classmethod
    def from_poscar(cls, poscar_path: str, pot_type: str, pot_map: dict = None):
        with open(poscar_path, 'r') as fin:
            for i in range(5):
                fin.readline()
            species_line = fin.readline()
            species_list = species_line.strip().split()
            pot_list = []
            for species in species_list:
                if pot_map is not None and species in pot_map:
                    pot_list.append(pot_map[species])
                elif species in recommended_pot_for_elem_except:
                    pot_list.append(recommended_pot_for_elem_except[species])
                else:
                    pot_list.append(species)
            return cls(pot_list, pot_type)

    def write(self, dest):
        cmd = 'cat '
        for pot in self.pot_list:
            if self.pot_type == 'pbe':
                cmd += f'{pot_pbe}/{pot}/POTCAR '
            elif self.pot_type == 'lda':
                cmd += f'{pot_lda}/{pot}/POTCAR '
            else:
                raise ValueError(f'pseudo potential for {self.pot_type} not supported!')
        cmd += '> ' + str(dest)
        subprocess.call(cmd, shell=True)


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='generate POTCAR from POSCAR, author: YCX')
    parser.add_argument('poscar', help='POSCAR file to use in calculation')
    parser.add_argument('-t', '--type', dest='type', default='pbe', help='pot type: pbe, lda')
    parser.add_argument('-o', '--output', dest='output', default='POTCAR', help='output POTCAR file')
    args = parser.parse_args()

    pot = Potcar.from_poscar(args.poscar, args.type)
    pot.write(args.output)


if __name__ == '__main__':
    main()
