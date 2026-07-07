"""
Tests for CP2K input file parser (Section / KeyValue).

Run: python3 -m pytest tests/test_cp2k_input.py
  or: python3 tests/test_cp2k_input.py
"""
from vaspauto.io.cp2k_input import Section, KeyValue


# ------------------------------------------------------------------
#  from_lines / from_str — parsing
# ------------------------------------------------------------------

def test_parse_simple_kv():
    """Single section with one key-value pair."""
    lines = [
        '&GLOBAL',
        '   PROJECT H2O',
        '&END',
    ]
    sec = Section.from_lines(lines)
    assert sec.get_kv('GLOBAL/PROJECT').strip() == 'H2O'


def test_parse_nested_section():
    """Nested sections."""
    lines = [
        '&FORCE_EVAL',
        '   &DFT',
        '       BASIS_SET_FILE_NAME BASIS_MOLOPT',
        '   &END DFT',
        '&END',
    ]
    sec = Section.from_lines(lines)
    assert sec.get_kv('FORCE_EVAL/DFT/BASIS_SET_FILE_NAME').strip() == 'BASIS_MOLOPT'


def test_parse_multiple_kvs():
    """Multiple key-value pairs in one section."""
    lines = [
        '&MOTION',
        '   &CELL_OPT',
        '       MAX_ITER 200',
        '       OPTIMIZER BFGS',
        '   &END',
        '&END',
    ]
    sec = Section.from_lines(lines)
    assert sec.get_kv('MOTION/CELL_OPT/MAX_ITER') == '200'
    assert sec.get_kv('MOTION/CELL_OPT/OPTIMIZER') == 'BFGS'


def test_parse_section_param():
    """Section with a parameter string."""
    lines = [
        '&FORCE_EVAL N',
        '   METHOD Quickstep',
        '&END',
    ]
    sec = Section.from_lines(lines)
    force_eval = sec.get_subsec('FORCE_EVAL')
    assert force_eval is not None
    assert force_eval.params == 'N'
    assert sec.get_kv('FORCE_EVAL/METHOD').strip() == 'Quickstep'


def test_parse_from_str():
    """from_str convenience method."""
    s = """&GLOBAL
  PROJECT water
  RUN_TYPE MD
&END
"""
    sec = Section.from_str(s)
    assert sec.get_kv('GLOBAL/PROJECT').strip() == 'water'
    assert sec.get_kv('GLOBAL/RUN_TYPE').strip() == 'MD'


def test_parse_empty_values():
    """Key with no value (should store as empty string)."""
    lines = ['&SECTION', '   FLAG', '&END']
    sec = Section.from_lines(lines)
    assert sec.get_kv('SECTION/FLAG') == ''


def test_parse_comment_lines():
    """Lines starting with ! or # should be ignored."""
    lines = [
        '! This is a comment',
        '# Also a comment',
        '&GLOBAL',
        '   PROJECT test  ! inline comment',
        '&END',
    ]
    sec = Section.from_lines(lines)
    assert sec.get_kv('GLOBAL/PROJECT').strip() == 'test'


def test_parse_empty_section():
    """An empty section (no children)."""
    lines = ['&EMPTY', '&END']
    sec = Section.from_lines(lines)
    empty = sec.get_subsec('EMPTY')
    assert empty is not None
    assert len(empty.kvs) == 0
    assert len(empty.subsecs) == 0


def test_parse_missing_ampersand_in_end():
    """&END without section name is fine."""
    lines = ['&GLOBAL', '   PROJECT x', '&END']
    sec = Section.from_lines(lines)
    assert sec.get_kv('GLOBAL/PROJECT') == 'x'


def test_parse_deeply_nested():
    """Deep nesting."""
    lines = [
        '&A',
        '   &B',
        '       &C',
        '           KEY val',
        '       &END',
        '   &END',
        '&END',
    ]
    sec = Section.from_lines(lines)
    assert sec.get_kv('A/B/C/KEY').strip() == 'val'


# ------------------------------------------------------------------
#  from_dict / to_dict
# ------------------------------------------------------------------

def test_from_dict():
    """from_dict creates correct structure."""
    sec = Section.from_dict({
        'GLOBAL': {'PROJECT': 'test', 'RUN_TYPE': 'MD'},
        'FORCE_EVAL': {
            '_': 'N',
            'METHOD': 'Quickstep',
            'DFT': {'BASIS_SET_FILE_NAME': 'BASIS_MOLOPT'},
        },
    })
    assert sec.get_kv('GLOBAL/PROJECT').strip() == 'test'
    assert sec.get_kv('GLOBAL/RUN_TYPE').strip() == 'MD'
    assert sec.get_kv('FORCE_EVAL/METHOD').strip() == 'Quickstep'
    assert sec.get_kv('FORCE_EVAL/DFT/BASIS_SET_FILE_NAME').strip() == 'BASIS_MOLOPT'
    # Section param
    force_eval = sec.get_subsec('FORCE_EVAL')
    assert force_eval is not None
    assert force_eval.params == 'N'


def test_to_dict():
    """Round-trip: from_dict -> to_dict preserves structure."""
    d = {
        'GLOBAL': {'PROJECT': 'test', 'RUN_TYPE': 'MD'},
        'FORCE_EVAL': {
            '_': 'N',
            'DFT': {'BASIS_SET_FILE_NAME': 'BASIS_MOLOPT'},
        },
    }
    sec = Section.from_dict(d)
    result = sec.to_dict()
    assert result == d


def test_from_dict_empty():
    """from_dict with empty dict yields top-level section."""
    sec = Section.from_dict({})
    assert len(sec.kvs) == 0
    assert len(sec.subsecs) == 0


# ------------------------------------------------------------------
#  set / insert / get / delete
# ------------------------------------------------------------------

def test_set_kv():
    """set() creates or overwrites a key-value pair."""
    sec = Section.from_dict({'GLOBAL': {'PROJECT': 'old'}})
    sec.set('GLOBAL/PROJECT', 'new')
    assert sec.get_kv('GLOBAL/PROJECT') == 'new'


def test_set_creates_path():
    """set() creates intermediate sections if they don't exist."""
    sec = Section.empty_sec_with_name('')
    sec.set('A/B/C', 'val')
    assert sec.get_kv('A/B/C') == 'val'


def test_set_with_list():
    """set() with a list creates multiple identical keys."""
    sec = Section.empty_sec_with_name('')
    sec.set('CELL/LONG-RANGE-TAU_CORRECTION', [True])
    # Should create one kv with value "True"
    assert sec.get_kv('CELL/LONG-RANGE-TAU_CORRECTION') == 'True'


def test_insert_kv():
    """insert() adds a key without overwriting existing."""
    sec = Section.from_dict({'GLOBAL': {'A': '1'}})
    sec.insert('GLOBAL/B', '2')
    assert sec.get_kv('GLOBAL/A') == '1'
    assert sec.get_kv('GLOBAL/B') == '2'


def test_insert_section():
    """insert() can add a subsection."""
    sec = Section.empty_sec_with_name('')
    sub = Section.empty_sec_with_name('NEW_SEC')
    sub.set('K', 'v')
    sec.insert('', sub)
    assert sec.get_kv('NEW_SEC/K') == 'v'


def test_delete_kv():
    """del_kv removes a key-value."""
    sec = Section.from_dict({'GLOBAL': {'A': '1', 'B': '2'}})
    sec.del_kv('GLOBAL/A')
    assert sec.get_kv('GLOBAL/A') is None
    assert sec.get_kv('GLOBAL/B') == '2'


def test_delete_subsec():
    """del_subsec removes a subsection."""
    sec = Section.from_dict({'A': {'B': {'K': 'v'}}})
    sec.del_subsec('A/B')
    assert sec.get_subsec('A/B') is None
    assert sec.get_subsec('A') is not None


def test_get_kv_nonexistent():
    """get_kv returns None for missing key."""
    sec = Section.from_dict({'A': {'B': 'val'}})
    assert sec.get_kv('A/MISSING') is None
    assert sec.get_kv('NONEXISTENT/K') is None


def test_get_subsec_nonexistent():
    """get_subsec returns None for missing section."""
    sec = Section.from_dict({'A': {}})
    assert sec.get_subsec('A/MISSING') is None


def test_set_param():
    """set_param sets the parameter string of a section."""
    sec = Section.from_dict({'FORCE_EVAL': {'_': 'old', 'METHOD': 'QS'}})
    sec.set_param('FORCE_EVAL', 'N')
    force_eval = sec.get_subsec('FORCE_EVAL')
    assert force_eval is not None
    assert force_eval.params == 'N'
    assert sec.get_param('FORCE_EVAL') == 'N'


def test_del_param():
    """del_param clears the parameter string."""
    sec = Section.from_dict({'FORCE_EVAL': {'_': 'N'}})
    sec.del_param('FORCE_EVAL')
    assert sec.get_param('FORCE_EVAL') == ''


# ------------------------------------------------------------------
#  update
# ------------------------------------------------------------------

def test_update_overwrites_kv():
    """update() overwrites existing keys with the source's values."""
    dst = Section.from_dict({'GLOBAL': {'PROJECT': 'old', 'RUN_TYPE': 'MD'}})
    src = Section.from_dict({'GLOBAL': {'PROJECT': 'new'}})
    dst.update(src)
    assert dst.get_kv('GLOBAL/PROJECT') == 'new'
    assert dst.get_kv('GLOBAL/RUN_TYPE') == 'MD'  # unchanged


def test_update_adds_new_subsec():
    """update() adds subsections that exist only in the source."""
    dst = Section.from_dict({'GLOBAL': {'PROJECT': 'test'}})
    src = Section.from_dict({'MOTION': {'CELL_OPT': {'MAX_ITER': '200'}}})
    dst.update(src)
    assert dst.get_kv('MOTION/CELL_OPT/MAX_ITER') == '200'
    assert dst.get_kv('GLOBAL/PROJECT') == 'test'


def test_update_merges_nested():
    """update() recursively merges nested subsections."""
    dst = Section.from_dict({
        'FORCE_EVAL': {
            'DFT': {'BASIS_SET_FILE_NAME': 'BASIS_MOLOPT'},
        },
    })
    src = Section.from_dict({
        'FORCE_EVAL': {
            'DFT': {'CUTOFF': '500'},
        },
    })
    dst.update(src)
    assert dst.get_kv('FORCE_EVAL/DFT/BASIS_SET_FILE_NAME') == 'BASIS_MOLOPT'
    assert dst.get_kv('FORCE_EVAL/DFT/CUTOFF') == '500'


# ------------------------------------------------------------------
#  iter_lines / to_str round-trip
# ------------------------------------------------------------------

def test_roundtrip_from_str_to_str():
    """Parse and serialize, then parse again — should be equivalent."""
    original = """&GLOBAL
  PROJECT water
  RUN_TYPE MD
  &FORCE_EVAL
    METHOD Quickstep
  &END
&END
"""
    sec1 = Section.from_str(original)
    serialized = sec1.to_str()
    sec2 = Section.from_str(serialized)
    assert sec2.get_kv('GLOBAL/PROJECT').strip() == 'water'
    assert sec2.get_kv('GLOBAL/RUN_TYPE').strip() == 'MD'
    assert sec2.get_kv('GLOBAL/FORCE_EVAL/METHOD').strip() == 'Quickstep'


def test_roundtrip_from_dict_to_dict():
    """from_dict then to_dict round-trips faithfully."""
    d = {
        'GLOBAL': {'PROJECT': 'water'},
        'FORCE_EVAL': {'_': 'N', 'DFT': {'BASIS_SET': 'DZVP'}},
    }
    sec = Section.from_dict(d)
    assert sec.to_dict() == d


def test_iter_lines_with_section_param():
    """iter_lines includes the section parameter in &SECTION line."""
    sec = Section.from_dict({'FORCE_EVAL': {'_': 'N', 'METHOD': 'QS'}})
    lines = list(sec.iter_lines(global_obj=True))
    force_line = [l for l in lines if 'FORCE_EVAL' in l][0]
    assert 'N' in force_line


# ------------------------------------------------------------------
#  Edge cases
# ------------------------------------------------------------------

def test_empty_top_level():
    """Empty top-level (name='') can contain both kvs and subsections."""
    sec = Section.from_dict({'K1': 'v1', 'SEC': {'K2': 'v2'}})
    assert sec.name == ''
    assert sec.get_kv('K1') == 'v1'
    assert sec.get_kv('SEC/K2') == 'v2'


def test_string_value_with_spaces():
    """Key values with internal spaces are preserved."""
    lines = ['&CELL', '   ABC 12.0 13.0 14.0', '&END']
    sec = Section.from_lines(lines)
    assert sec.get_kv('CELL/ABC').strip() == '12.0 13.0 14.0'


def test_update_params():
    """update() also overwrites section params."""
    dst = Section.from_dict({'FORCE_EVAL': {'_': 'N'}})
    src = Section.from_dict({'FORCE_EVAL': {'_': 'Y'}})
    dst.update(src)
    assert dst.get_param('FORCE_EVAL') == 'Y'


# ------------------------------------------------------------------
#  Smoke test: real CP2K snippet
# ------------------------------------------------------------------

def test_real_cp2k_snippet():
    """A small realistic CP2K input fragment."""
    src = """
&GLOBAL
  PROJECT bulk_H2O
  RUN_TYPE ENERGY
&END
&FORCE_EVAL
  METHOD Quickstep
  &DFT
    BASIS_SET_FILE_NAME BASIS_MOLOPT
    POTENTIAL_FILE_NAME POTENTIAL
    &MGRID
      CUTOFF 400
      REL_CUTOFF 60
    &END MGRID
  &END DFT
&END FORCE_EVAL
"""
    sec = Section.from_str(src)
    assert sec.get_kv('GLOBAL/PROJECT').strip() == 'bulk_H2O'
    assert sec.get_kv('GLOBAL/RUN_TYPE').strip() == 'ENERGY'
    assert sec.get_kv('FORCE_EVAL/METHOD').strip() == 'Quickstep'
    assert sec.get_kv('FORCE_EVAL/DFT/BASIS_SET_FILE_NAME').strip() == 'BASIS_MOLOPT'
    assert sec.get_kv('FORCE_EVAL/DFT/MGRID/CUTOFF').strip() == '400'
    assert sec.get_kv('FORCE_EVAL/DFT/MGRID/REL_CUTOFF').strip() == '60'

    # Round-trip
    serialized = sec.to_str()
    sec2 = Section.from_str(serialized)
    assert sec2.get_kv('GLOBAL/PROJECT').strip() == 'bulk_H2O'
    assert sec2.get_kv('FORCE_EVAL/DFT/MGRID/CUTOFF').strip() == '400'


if __name__ == '__main__':
    test_parse_simple_kv()
    test_parse_nested_section()
    test_parse_multiple_kvs()
    test_parse_section_param()
    test_parse_from_str()
    test_parse_empty_values()
    test_parse_comment_lines()
    test_parse_empty_section()
    test_parse_missing_ampersand_in_end()
    test_parse_deeply_nested()
    test_from_dict()
    test_to_dict()
    test_from_dict_empty()
    test_set_kv()
    test_set_creates_path()
    test_set_with_list()
    test_insert_kv()
    test_insert_section()
    test_delete_kv()
    test_delete_subsec()
    test_get_kv_nonexistent()
    test_get_subsec_nonexistent()
    test_set_param()
    test_del_param()
    test_update_overwrites_kv()
    test_update_adds_new_subsec()
    test_update_merges_nested()
    test_roundtrip_from_str_to_str()
    test_roundtrip_from_dict_to_dict()
    test_iter_lines_with_section_param()
    test_empty_top_level()
    test_string_value_with_spaces()
    test_update_params()
    test_real_cp2k_snippet()
    print('\nAll CP2K input tests passed!')
