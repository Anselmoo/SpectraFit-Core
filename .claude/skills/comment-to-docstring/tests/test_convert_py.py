from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "scripts" / "convert_py.py"
_SPEC = importlib.util.spec_from_file_location("convert_py", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
import sys
sys.modules["convert_py"] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_module_leading_comments_become_module_docstring() -> None:
    source = "# A module.\n# With two lines.\n\nvalue = 1\n"
    transformed, report = _MODULE.convert_source(source)
    tree = ast.parse(transformed)
    assert ast.get_docstring(tree) == "A module.\nWith two lines."
    assert len(report["converted"]) == 1


def test_declaration_leading_comments_become_function_docstring() -> None:
    source = "# module\n\ndef work(x):\n    # calculate the result\n    # carefully\n    return x + 1\n"
    transformed, report = _MODULE.convert_source(source)
    tree = ast.parse(transformed)
    function = tree.body[1]
    assert isinstance(function, ast.FunctionDef)
    assert ast.get_docstring(function) == "calculate the result\ncarefully"
    assert report["converted"][1]["owner"] == "function"


def test_existing_docstring_is_preserved_by_default_and_replaced_explicitly() -> None:
    source = "def work():\n    # new\n    \"\"\"old\"\"\"\n    return 1\n"
    unchanged, report = _MODULE.convert_source(source)
    assert '"""old"""' in unchanged
    assert report["skipped"][0]["reason"] == "existing docstring preserved"
    replaced, _ = _MODULE.convert_source(source, replace_existing=True)
    assert ast.get_docstring(ast.parse(replaced).body[0]) == "new"


def test_inline_comments_are_not_falsely_called_docstrings() -> None:
    source = "def work():\n    result = 1\n    # explain the result\n    return result\n"
    transformed, report = _MODULE.convert_source(source)
    assert transformed == source
    assert report["skipped"][0]["reason"] == "not module- or declaration-leading"


def test_runner_style_inline_comments_remain_unchanged() -> None:
    source = "def rung(wires):\n    statuses = {w.status for w in wires}\n    if 'fail' in statuses:\n        return 2  # any genuine failure caps the rung\n"
    transformed, report = _MODULE.convert_source(source)
    assert transformed == source
    assert report["converted"] == []
