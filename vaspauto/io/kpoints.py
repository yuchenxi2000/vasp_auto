from os import PathLike


def write_auto_gen_k_mesh(file: PathLike, nk_list: list):
    fout = open(file, 'w')
    fout.write('A\n')
    fout.write('0\n')
    fout.write('Gamma\n')
    for k_idx in range(3):
        fout.write(str(nk_list[k_idx]))
        fout.write('\n' if k_idx == 2 else ' ')
    fout.write('0 0 0\n')
    fout.close()
