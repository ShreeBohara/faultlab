"""smolagents is imported only through the adapter's dotenv guard (static check, no import).

smolagents 1.26.0 calls python-dotenv's load_dotenv() on first import, which from this
project's .venv reaches the real faultlab/.env and copies its credentials into os.environ.
``app.integrations.external_agent._import_smolagents`` performs that first import with
load_dotenv disabled. The guard only protects its own import site: if any other module
imported smolagents first, the values would already be exported (September 28 review).
This test parses every FaultLab Python source file outside the test suite and fails if
smolagents is imported anywhere except (a) inside ``_import_smolagents`` itself, or (b) in
a function of external_agent.py after that function has called ``_import_smolagents()``.
"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ADAPTER = ROOT / 'backend/app/integrations/external_agent.py'
SOURCES = sorted([*(ROOT / 'backend/app').rglob('*.py'), *(ROOT / 'scripts').rglob('*.py')])
IMPORTERS = {'import_module', '__import__'}


def _smolagents(name):
    return isinstance(name, str) and (name == 'smolagents' or name.startswith('smolagents.'))


def _imports(tree):
    """(node, enclosing function or None) for every smolagents import in ``tree``."""
    found = []

    def visit(node, function):
        for child in ast.iter_child_nodes(node):
            inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            if isinstance(child, ast.Import) and any(_smolagents(alias.name) for alias in child.names):
                found.append((child, function))
            elif isinstance(child, ast.ImportFrom) and _smolagents(child.module):
                found.append((child, function))
            elif isinstance(child, ast.Call):
                target = child.func.attr if isinstance(child.func, ast.Attribute) else getattr(child.func, 'id', None)
                if (target in IMPORTERS and child.args and isinstance(child.args[0], ast.Constant)
                        and _smolagents(child.args[0].value)):
                    found.append((child, function))
            visit(child, inner)
    visit(tree, None)
    return found


def _guard_called_before(function, node):
    for statement in function.body:
        if statement.lineno >= node.lineno:
            return False
        for inner in ast.walk(statement):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                    and inner.func.id == '_import_smolagents'):
                return True
    return False


def violations(path, source):
    bad = []
    for node, function in _imports(ast.parse(source, filename=str(path))):
        allowed = path == ADAPTER and function is not None and (
            (function.name == '_import_smolagents' and isinstance(node, ast.Call))
            or _guard_called_before(function, node))
        if not allowed:
            bad.append(f'{path.relative_to(ROOT)}:{node.lineno}')
    return bad


def test_scan_covers_the_backend_and_scripts():
    assert ADAPTER in SOURCES and len(SOURCES) > 100


def test_smolagents_is_imported_only_behind_the_dotenv_guard():
    bad = [item for path in SOURCES for item in violations(path, path.read_text())]
    assert bad == [], f'smolagents imported outside the dotenv guard: {bad}'


def test_the_adapter_really_uses_the_guard_before_its_imports():
    tree = ast.parse(ADAPTER.read_text())
    found = _imports(tree)
    assert any(function and function.name == '_import_smolagents' for _, function in found)
    assert any(function and function.name != '_import_smolagents' for _, function in found)


@pytest.mark.parametrize('source', [
    'import smolagents\n',
    'from smolagents import ToolCallingAgent\n',
    'def f():\n    from smolagents.models import ChatMessage\n',
    'import importlib\nimportlib.import_module("smolagents")\n',
    'def f():\n    __import__("smolagents.agents")\n',
    'def f():\n    from smolagents import Tool\n    _import_smolagents()\n',  # guard called too late
])
def test_the_check_catches_unguarded_imports(source):
    assert violations(ADAPTER, source), source
    assert violations(ROOT / 'backend/app/other.py', source), source


def test_the_check_allows_the_guarded_pattern():
    source = ('def _import_smolagents():\n    importlib.import_module("smolagents")\n'
              'def build():\n    _import_smolagents()\n    from smolagents import Tool\n')
    assert violations(ADAPTER, source) == []
    assert violations(ROOT / 'backend/app/other.py', source)  # only the adapter may do it
