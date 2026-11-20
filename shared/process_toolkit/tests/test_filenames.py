from process_toolkit.filenames import safe_filename_component


def test_collapses_whitespace_to_underscores():
    assert safe_filename_component("My File") == "My_File"


def test_strips_single_and_double_quotes_entirely():
    # CONFIRMED AS A REAL BUG: an LLM-supplied filename sometimes wraps a name
    # containing a space in quotes (e.g. "'My File'"). Spaces were already
    # collapsed to underscores, but the quote characters themselves leaked
    # straight into the saved filename -- poorly handled on both Windows and
    # Linux -- instead of being removed.
    assert safe_filename_component("'My File'") == "My_File"
    assert safe_filename_component('"My File"') == "My_File"
    assert safe_filename_component("'main.tf'") == "main.tf"


def test_replaces_windows_reserved_characters_with_underscores():
    assert safe_filename_component("a/b:c") == "a_b_c"
    assert safe_filename_component('a<b>c|d*e?f') == "a_b_c_d_e_f"


def test_strips_leading_and_trailing_dots_and_underscores():
    assert safe_filename_component("..hidden__") == "hidden"


def test_falls_back_to_untitled_for_empty_or_non_string_input():
    assert safe_filename_component("") == "untitled"
    assert safe_filename_component("   ") == "untitled"
    assert safe_filename_component(None) == "untitled"


def test_caps_length():
    long_name = "a" * 300
    assert len(safe_filename_component(long_name)) == 150
