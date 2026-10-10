"""smolagents is imported only through the adapter's dotenv guard (static check, no import).

smolagents 1.26.0 calls python-dotenv's load_dotenv() on first import, which from this
project's .venv reaches the real faultlab/.env and copies its credentials into os.environ.
``app.integrations.external_agent._import_smolagents`` performs that first import with
load_dotenv disabled. The guard only protects its own import site: if any other module
imported smolagents first, the values would already be exported (September 28 review).
This test parses every FaultLab Python source file outside the test suite and fails if
smolagents is imported anywhere except (a) inside ``_import_smolagents`` itself, (b) in
a function of external_agent.py after that function has called ``_import_smolagents()``,
or (c) in the native dependency worker's exact unconditional inline guard block.
The worker exception applies to those guarded import nodes, never its whole file.
"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ADAPTER = ROOT / 'backend/app/integrations/external_agent.py'
WORKER = ROOT / 'backend/app/native_agents/worker.py'
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


WORKER_GUARD = ast.parse(
    'import dotenv\n'
    'import dotenv.main\n'
    'dotenv.load_dotenv = dotenv.main.load_dotenv = lambda *a, **kw: False\n'
).body
WORKER_WITH = ast.parse('with contextlib.redirect_stdout(sys.stderr):\n    pass\n').body[0].items


def _same_ast(actual, expected):
    return ast.dump(actual, include_attributes=False) == ast.dump(expected, include_attributes=False)


def _worker_guarded_nodes(tree):
    """Only direct imports dominated by the worker's reviewed inline guard.

    A guard in another branch, a partial replacement, an intervening statement,
    or a restore before import does not match. No user code or dependencies run.
    """
    allowed = set()
    for function in tree.body:
        if not isinstance(function, ast.FunctionDef) or function.name != 'main':
            continue
        for block in function.body:
            if (not isinstance(block, ast.With) or len(block.items) != len(WORKER_WITH)
                    or not all(_same_ast(item, expected) for item, expected in zip(block.items, WORKER_WITH))
                    or len(block.body) <= len(WORKER_GUARD)
                    or not all(_same_ast(statement, expected)
                               for statement, expected in zip(block.body, WORKER_GUARD))):
                continue
            imports = block.body[len(WORKER_GUARD):]
            if all((isinstance(node, ast.ImportFrom) and _smolagents(node.module))
                   or (isinstance(node, ast.Import) and all(_smolagents(alias.name) for alias in node.names))
                   for node in imports):
                allowed.update(imports)
    return allowed


def violations(path, source):
    bad = []
    tree = ast.parse(source, filename=str(path))
    worker_guarded = _worker_guarded_nodes(tree) if path == WORKER else set()
    for node, function in _imports(tree):
        allowed = path == ADAPTER and function is not None and (
            (function.name == '_import_smolagents' and isinstance(node, ast.Call))
            or _guard_called_before(function, node))
        allowed = allowed or node in worker_guarded
        if not allowed:
            bad.append(f'{path.relative_to(ROOT)}:{node.lineno}')
    return bad


def test_scan_covers_the_backend_and_scripts():
    assert ADAPTER in SOURCES and WORKER in SOURCES and len(SOURCES) > 100


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


def _worker_source(body):
    return 'def main():\n    with contextlib.redirect_stdout(sys.stderr):\n' + ''.join(
        '        ' + line + '\n' for line in body.splitlines())


INLINE_GUARD = ('import dotenv\nimport dotenv.main\n'
                'dotenv.load_dotenv = dotenv.main.load_dotenv = lambda *a, **kw: False\n')


def test_the_worker_exception_requires_its_exact_guarded_import_nodes():
    source = _worker_source(INLINE_GUARD + 'from smolagents import Tool\nfrom smolagents.models import ChatMessage')
    assert violations(WORKER, source) == []
    assert violations(ADAPTER, source)
    assert violations(ROOT / 'backend/app/other.py', source)
    assert violations(WORKER, WORKER.read_text()) == []
    # A valid block never exempts an additional import elsewhere in this file.
    assert violations(WORKER, source + '\nimport smolagents\n')


@pytest.mark.parametrize('body', [
    'from smolagents import Tool',  # no guard
    'from smolagents import Tool\n' + INLINE_GUARD,  # late guard
    'import dotenv\nimport dotenv.main\ndotenv.load_dotenv = lambda *a, **kw: False\nfrom smolagents import Tool',
    'import dotenv\nimport dotenv.main\ndotenv.main.load_dotenv = lambda *a, **kw: False\nfrom smolagents import Tool',
    INLINE_GUARD.replace('lambda *a, **kw: False', 'lambda *a, **kw: True') + 'from smolagents import Tool',
    INLINE_GUARD.replace('lambda *a, **kw: False', 'lambda *a, **kw: False if enabled else True') + 'from smolagents import Tool',
    'import dotenv\nimport dotenv.main\nif enabled:\n    dotenv.load_dotenv = dotenv.main.load_dotenv = lambda *a, **kw: False\nfrom smolagents import Tool',
    INLINE_GUARD + 'dotenv.load_dotenv = original\nfrom smolagents import Tool',
    INLINE_GUARD + 'dotenv.main.load_dotenv = original\nfrom smolagents import Tool',
    INLINE_GUARD + 'if enabled:\n    from smolagents import Tool',
    INLINE_GUARD + 'run_user_code()\nfrom smolagents import Tool',
    INLINE_GUARD + 'importlib.import_module("smolagents")',
])
def test_worker_scanner_rejects_missing_late_partial_or_conditional_guards(body):
    assert violations(WORKER, _worker_source(body))


def test_worker_scanner_rejects_guarded_block_in_a_conditional_or_different_function():
    source = _worker_source(INLINE_GUARD + 'from smolagents import Tool')
    assert violations(WORKER, source.replace('def main():', 'def other():'))
    conditional = 'def main():\n    if enabled:\n' + ''.join(
        '    ' + line + '\n' for line in source.splitlines()[1:])
    assert violations(WORKER, conditional)
