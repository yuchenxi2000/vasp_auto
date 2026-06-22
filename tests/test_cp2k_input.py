from vaspauto.io.cp2k_input import Section


def test_case1():
    lines = [
        '&SEC1 NO',
        '   K1 1 2 3',
        '   &SEC2',
        '       K2 a c 2',
        '   &END',
        '   K3 0',
        '&END',
    ]
    sec = Section.from_lines(lines)
    assert sec.get_kv('SEC1/K1') == '1 2 3'
    assert sec.get_kv('SEC1/SEC2/K2') == 'a c 2'
    sec.get_subsec('SEC1').set('K1', 'hahaha')
    assert sec.get_kv('SEC1/K1') == 'hahaha'
    sec.set('SEC1/SEC2/K2', '666 233')
    assert sec.get_kv('SEC1/SEC2/K2') == '666 233'


def test_case2():
    sec = Section.from_dict({
        'SEC1': {
            'K2': 1,
            'K3': 2,
            'SEC2': {
                '_': 'NO',
                'sec4': 'a'
            },
        },
        'SEC3': {'K0': 'hahaha'},
        'K233': '666'
    })

    sec2 = Section.from_dict({
        'SEC1': {
            'KK': 3,
            'K3': 'a',
            'SEC2': {
                '_': 'YES',
                'sec4': 'a',
                'sss': {
                    'll': 555,
                },
            },
            'SEC5': {
                's': 'g'
            },
        },
        'K23333': '666666'
    })

    sec.update(sec2)
    # TODO
    print(sec)
    # print(sec2)


if __name__ == '__main__':
    test_case1()
    test_case2()
