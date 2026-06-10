"""
Tests for INCAR parser (including VASP 6 nested tags).
Run: python3 -m pytest incar_parser_test.py
  or: PYTHONPATH=. python3 incar_parser_test.py
"""
from vaspauto.incar_parser import Incar


def test_parse_flat():
    """Backward compatibility: flat INCAR format."""
    incar_str = """
    NSW = 100
    IBRION = 2
    ISIF = 3
    """
    incar = Incar.from_str(incar_str)
    assert incar.get('NSW') == '100', f"Expected '100', got {incar.get('NSW')}"
    assert incar.get('IBRION') == '2'
    assert incar.get('ISIF') == '3'
    print('✓ test_parse_flat')


def test_parse_flat_with_comments():
    """Flat INCAR with comments and # inline."""
    incar_str = """
    # This is a comment
    NSW = 100  # inline comment
    ! VASP comment style
    IBRION = 2
    """
    incar = Incar.from_str(incar_str)
    assert incar.get('NSW') == '100'
    assert incar.get('IBRION') == '2'
    print('✓ test_parse_flat_with_comments')


def test_parse_flat_with_semicolon():
    """; used as line separator."""
    incar_str = "NSW = 100; IBRION = 2; ISIF = 3"
    incar = Incar.from_str(incar_str)
    assert incar.get('NSW') == '100'
    assert incar.get('IBRION') == '2'
    assert incar.get('ISIF') == '3'
    print('✓ test_parse_flat_with_semicolon')


def test_parse_flat_with_continuation():
    """Backslash line continuation."""
    incar_str = "SYSTEM = line1 \\\nline2 \\\nline3\nNSW = 100\n"
    incar = Incar.from_str(incar_str)
    assert incar.get('SYSTEM') == 'line1 line2 line3'
    assert incar.get('NSW') == '100'
    print('✓ test_parse_flat_with_continuation')


def test_parse_flat_quoted_string():
    """Multi-line quoted string."""
    incar_str = 'SYSTEM = "multi\nline\nstring"\nNSW = 100\n'
    incar = Incar.from_str(incar_str)
    assert incar.get('SYSTEM') == 'multi\nline\nstring'
    assert incar.get('NSW') == '100'
    print('✓ test_parse_flat_quoted_string')


def test_parse_single_nested():
    """Single-level nested block."""
    incar_str = """
    NSW = 100
    KERNEL_TRUNCATION {
        LTRUNCATE = T
        IDIMENSIONALITY = 0
        LCOARSEN = T
    }
    IBRION = 2
    """
    incar = Incar.from_str(incar_str)
    assert incar.get('NSW') == '100'
    assert incar.get('KERNEL_TRUNCATION/LTRUNCATE') == 'T'
    assert incar.get('KERNEL_TRUNCATION/IDIMENSIONALITY') == '0'
    assert incar.get('KERNEL_TRUNCATION/LCOARSEN') == 'T'
    assert incar.get('IBRION') == '2'
    print('✓ test_parse_single_nested')


def test_parse_multi_nested():
    """Multi-level nested blocks."""
    incar_str = """
    NSW = 100
    OUTER {
        MIDDLE {
            INNER = 42
        }
        FLAT_KEY = yes
    }
    """
    incar = Incar.from_str(incar_str)
    assert incar.get('NSW') == '100'
    assert incar.get('OUTER/MIDDLE/INNER') == '42'
    assert incar.get('OUTER/FLAT_KEY') == 'yes'
    print('✓ test_parse_multi_nested')


def test_parse_multiple_sections():
    """Multiple sibling nested blocks."""
    incar_str = """
    SEC_A {
        KEY1 = 1
    }
    SEC_B {
        KEY2 = 2
    }
    NSW = 100
    """
    incar = Incar.from_str(incar_str)
    assert incar.get('SEC_A/KEY1') == '1'
    assert incar.get('SEC_B/KEY2') == '2'
    assert incar.get('NSW') == '100'
    print('✓ test_parse_multiple_sections')


def test_parse_empty_block():
    """Empty block should not crash."""
    incar_str = """
    NSW = 100
    EMPTY {
    }
    IBRION = 2
    """
    incar = Incar.from_str(incar_str)
    assert incar.get('NSW') == '100'
    assert incar.get('IBRION') == '2'
    print('✓ test_parse_empty_block')


def test_parse_nested_with_semicolons():
    """Semicolons as separators inside nested blocks."""
    incar_str = "NSW = 100; SEC { A = 1; B = 2 }; IBRION = 3"
    incar = Incar.from_str(incar_str)
    assert incar.get('NSW') == '100'
    assert incar.get('SEC/A') == '1'
    assert incar.get('SEC/B') == '2'
    assert incar.get('IBRION') == '3'
    print('✓ test_parse_nested_with_semicolons')


def test_roundtrip_flat():
    """Round-trip: parse flat INCAR, write back, parse again."""
    original = """NSW = 100
IBRION = 2
ISIF = 3
"""
    incar1 = Incar.from_str(original)
    output = str(incar1)
    incar2 = Incar.from_str(output)
    assert incar2.get('NSW') == '100'
    assert incar2.get('IBRION') == '2'
    assert incar2.get('ISIF') == '3'
    print('✓ test_roundtrip_flat')


def test_roundtrip_nested():
    """Round-trip: parse nested INCAR, write back, parse again."""
    original = """NSW = 100
KERNEL_TRUNCATION {
    LTRUNCATE = T
    LCOARSEN = T
}
IBRION = 2
"""
    incar1 = Incar.from_str(original)
    output = str(incar1)
    incar2 = Incar.from_str(output)
    assert incar2.get('NSW') == '100'
    assert incar2.get('KERNEL_TRUNCATION/LTRUNCATE') == 'T'
    assert incar2.get('KERNEL_TRUNCATION/LCOARSEN') == 'T'
    assert incar2.get('IBRION') == '2'
    print('✓ test_roundtrip_nested')


def test_roundtrip_multi_nested():
    """Round-trip multi-level nested blocks."""
    original = """OUTER {
    MIDDLE {
        INNER = 42
    }
}
NSW = 100
"""
    incar1 = Incar.from_str(original)
    output = str(incar1)
    incar2 = Incar.from_str(output)
    assert incar2.get('OUTER/MIDDLE/INNER') == '42'
    assert incar2.get('NSW') == '100'
    print('✓ test_roundtrip_multi_nested')


def test_set_nested_key():
    """Programmatically set a nested key and verify output."""
    incar = Incar.from_str("NSW = 100\n")
    incar.set('KERNEL_TRUNCATION/LTRUNCATE', 'T')
    incar.set('KERNEL_TRUNCATION/LCOARSEN', 'T')
    output = str(incar)
    assert 'KERNEL_TRUNCATION {' in output
    assert 'LTRUNCATE = T' in output
    assert 'LCOARSEN = T' in output
    # Parse back
    incar2 = Incar.from_str(output)
    assert incar2.get('KERNEL_TRUNCATION/LTRUNCATE') == 'T'
    assert incar2.get('NSW') == '100'
    print('✓ test_set_nested_key')


def test_del_nested_key():
    """Delete a nested key."""
    incar = Incar.from_str("""
    NSW = 100
    SEC {
        A = 1
        B = 2
    }
    """)
    assert incar.get('SEC/A') == '1'
    incar.del_key('SEC/A')
    output = str(incar)
    assert 'A = 1' not in output
    assert 'B = 2' in output
    assert 'NSW = 100' in output
    print('✓ test_del_nested_key')


def test_del_entire_section():
    """Delete all keys in a section removes the section block."""
    incar = Incar.from_str("""
    NSW = 100
    SEC {
        A = 1
    }
    """)
    incar.del_key('SEC/A')
    output = str(incar)
    assert 'SEC {' not in output  # Section removed since empty
    assert 'NSW = 100' in output
    print('✓ test_del_entire_section')


def test_duplicate_keys():
    """Duplicate keys (existing behavior preserved)."""
    incar_str = "A = 0; A = 1"
    incar = Incar.from_str(incar_str)
    # get() returns first value
    assert incar.get('A') == '0'
    # iter_lines outputs both
    output = str(incar)
    assert output.count('A =') == 2
    print('✓ test_duplicate_keys')


def test_comments_inside_block():
    """Comments inside nested blocks."""
    incar_str = """
    NSW = 100
    SEC {
        # comment line
        A = 1
        ! another comment
        B = 2
    }
    """
    incar = Incar.from_str(incar_str)
    assert incar.get('SEC/A') == '1'
    assert incar.get('SEC/B') == '2'
    print('✓ test_comments_inside_block')


def test_real_vasp6_example():
    """Real VASP 6 KERNEL_TRUNCATION example."""
    incar_str = """
    ENCUT = 520
    KERNEL_TRUNCATION {
        LTRUNCATE = T
        IDIMENSIONALITY = 0
        LCOARSEN = T
    }
    LREAL = Auto
    """
    incar = Incar.from_str(incar_str)
    assert incar.get('ENCUT') == '520'
    assert incar.get('KERNEL_TRUNCATION/LTRUNCATE') == 'T'
    assert incar.get('KERNEL_TRUNCATION/IDIMENSIONALITY') == '0'
    assert incar.get('KERNEL_TRUNCATION/LCOARSEN') == 'T'
    assert incar.get('LREAL') == 'Auto'

    # Round trip
    output = str(incar)
    incar2 = Incar.from_str(output)
    assert incar2.get('KERNEL_TRUNCATION/LTRUNCATE') == 'T'
    assert incar2.get('LREAL') == 'Auto'
    print('✓ test_real_vasp6_example')


if __name__ == '__main__':
    test_parse_flat()
    test_parse_flat_with_comments()
    test_parse_flat_with_semicolon()
    test_parse_flat_with_continuation()
    test_parse_flat_quoted_string()
    test_parse_single_nested()
    test_parse_multi_nested()
    test_parse_multiple_sections()
    test_parse_empty_block()
    test_parse_nested_with_semicolons()
    test_roundtrip_flat()
    test_roundtrip_nested()
    test_roundtrip_multi_nested()
    test_set_nested_key()
    test_del_nested_key()
    test_del_entire_section()
    test_duplicate_keys()
    test_comments_inside_block()
    test_real_vasp6_example()
    print('\n✅ All tests passed!')
