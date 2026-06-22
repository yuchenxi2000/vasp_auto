# 两个POSCAR线性插值，处理前后晶格不同时先转成晶格常数/夹角差值，然后对晶格常数/夹角差值
# （不同于VTST的dist.pl的处理，dist.pl直接对矩阵线性差值）
import numpy as np
import argparse
import copy

from vaspauto.io.poscar import Poscar


def pbc_min_vec(vec: np.ndarray, lat_mat: np.ndarray):
    vec = vec % np.full(3, 1.0)
    vec_cart = vec @ lat_mat  # to Cartesian coordinates
    lat_vec = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 1.0, 0.0],
        [0.0, 1.0, 1.0],
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 0.0],
        [1.0, 1.0, 1.0],
    ])  # (8, 3)
    lat_vec_cart = lat_vec @ lat_mat  # to Cartesian coordinates
    rel_vec = np.expand_dims(vec, -1) - lat_vec.T  # (Nv, 3, 8)
    rel_vec_cart = np.expand_dims(vec_cart, -1) - lat_vec_cart.T  # (Nv, 3, 8)
    rel_vec_norm = np.linalg.norm(rel_vec_cart, axis=-2)  # (Nv, 8)
    rel_vec_norm_min_arg = np.argmin(rel_vec_norm, axis=-1)  # Nv
    ind = np.expand_dims(rel_vec_norm_min_arg, axis=(-1, -2))  # (Nv, 1, 1)
    return np.take_along_axis(rel_vec, ind, axis=-1)[:, :, 0]


def mat2abc(R: np.ndarray) -> np.ndarray:
    abc_arr = np.zeros(6)
    for i in range(3):
        abc_arr[i] = np.linalg.norm(R[i, :])
    dot_idx = ((1, 2), (2, 0), (0, 1))
    for i, idx in enumerate(dot_idx):
        abc_arr[i] = np.arccos(R[idx[0], :] @ R[idx[1], :] / dot_idx[idx[0]] / dot_idx[idx[1]])
    return abc_arr


def abc2mat(abc) -> np.ndarray:
    R = np.zeros([3, 3])
    a = abc[0]
    b = abc[1]
    c = abc[2]
    alpha = abc[3]
    beta = abc[4]
    gamma = abc[5]
    cos = np.cos
    sin = np.sin
    sqrt = np.sqrt
    cos_d = (cos(alpha) - cos(beta) * cos(gamma)) / (sin(beta) * sin(gamma))
    if cos_d > 1:
        cos_d = 1
    elif cos_d < -1:
        cos_d = -1
    sin_d = sqrt(1 - cos_d ** 2)
    R[0, 0] = a
    R[1, 0] = b * cos(gamma)
    R[1, 1] = b * sin(gamma)
    R[2, 0] = c * cos(beta)
    R[2, 1] = c * sin(beta) * cos_d
    R[2, 2] = c * sin(beta) * sin_d
    return R


def interp2(lat_path: list[Poscar], num_images: int, fix_method: str = 'None', no_start_point: bool = False, no_end_point: bool = False):
    """
    interpolate two structures
    :param lat_path:
    :param num_images:
    :param fix_method: None: don't fix; Old_Simple: old fix method; Wigner_Sitz: Wigner-Sitz based algorithm
    :param no_start_point:
    :param no_end_point:
    :return:
    """
    images = []

    # if we interpolate the coordinates of atoms without fixing the path,
    # the atoms may not move along the path with the minimum distance.
    # e.g. the atom may move along the path: 0.9, 0.89, 0.88, ..., 0.1, which is obviously a wrong path,
    # compared with the correct path 0.9, 0.91, 0.92, ..., 1.1
    if fix_method == 'Old_Simple':
        # old algorithm
        for i in range(len(lat_path)):
            lat_path[i].warp_coord()
            if i != 0:
                lat_path[i].atoms = np.where(lat_path[i].atoms - lat_path[i-1].atoms > 0.5, lat_path[i].atoms - 1, lat_path[i].atoms)
                lat_path[i].atoms = np.where(lat_path[i].atoms - lat_path[i-1].atoms < -0.5, lat_path[i].atoms + 1, lat_path[i].atoms)
    elif fix_method == 'Wigner_Sitz':
        for i in range(len(lat_path)):
            lat_path[i].to_direct()
            if i != 0:
                lat_path[i].atoms = lat_path[i-1].atoms + pbc_min_vec(lat_path[i].atoms - lat_path[i-1].atoms, lat_path[i-1].lattice_vector)
    elif fix_method == 'None':
        pass
    else:
        raise ValueError(f'unknown fix method {fix_method}!')

    for i in range(1, len(lat_path)):
        lati = lat_path[i - 1]
        latf = lat_path[i]
        abcanglei = np.array(mat2abc(lati.lattice_vector))
        abcanglef = np.array(mat2abc(latf.lattice_vector))
        atomi = lati.atoms
        atomf = latf.atoms
        for j in range(0, num_images + 1):
            if no_start_point and i == 1 and j == 0:
                continue
            abcangle = abcanglef * j / (num_images + 1) + abcanglei * (1 - j / (num_images + 1))
            latm = copy.deepcopy(lati)
            latm.lattice_vector = abc2mat(abcangle)
            latm.atoms = atomf * j / (num_images + 1) + atomi * (1 - j / (num_images + 1))
            images.append(latm)
    if not no_end_point:
        images.append(copy.deepcopy(lat_path[-1]))

    return images


def main2():
    parser = argparse.ArgumentParser(description='interpolate two structures')
    parser.add_argument('-i', '--init', help='initial poscar file')
    parser.add_argument('-f', '--final', help='final poscar file')
    parser.add_argument('-n', '--num', type=int, help='number of intermediate structures', required=True)
    parser.add_argument('-d', '--dir', help='output directory', required=True)
    parser.add_argument('--prec', help='output precision')
    parser.add_argument('--fix', help='', action='store_true')
    parser.add_argument('--old-fix', dest='old_fix', help='', action='store_true')
    parser.add_argument('--no-endpoint', dest='no_endpoint', help='', action='store_true')
    parser.add_argument('--no-startpoint', dest='no_startpoint', help='', action='store_true')
    parser.add_argument('--start-idx', dest='start_idx', type=int)
    parser.add_argument('-p', '--path', nargs='+', help='path')
    args = parser.parse_args()

    if args.prec:
        prec = int(args.prec)
        np.set_printoptions(precision=prec)
    else:
        np.set_printoptions(precision=10)

    if args.path:
        path = args.path
    elif args.init and args.final:
        path = [args.init, args.final]
    else:
        parser.error('please provide path or initial and final states!')

    N = args.num
    out_dir = args.dir
    orig_images = []
    for image_file_path in path:
        orig_images.append(Poscar.from_file(image_file_path))

    if args.old_fix:
        fix_method = 'Old_Simple'
    elif args.fix:
        fix_method = 'Wigner_Sitz'
    else:
        fix_method = 'None'

    images = interp2(orig_images, N, fix_method, args.no_startpoint, args.no_endpoint)

    if args.start_idx:
        start_idx = args.start_idx
    else:
        start_idx = 0
    start_idx += 1 if args.no_startpoint else 0

    for i in range(len(images)):
        images[i].write_POSCAR(out_dir + f'/POSCAR_{i + start_idx:02}')


if __name__ == '__main__':
    main2()
