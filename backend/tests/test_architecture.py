"""静态检查模块依赖，阻止新增代码越层或形成循环依赖。"""

import ast
import importlib.util
from pathlib import Path

MODULES = Path(__file__).resolve().parents[1] / "modules"


def imports(path):
    module = "backend.modules." + ".".join(path.relative_to(MODULES).with_suffix("").parts)
    package = module.rsplit(".", 1)[0]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            name = "." * node.level + (node.module or "")
            base = importlib.util.resolve_name(name, package) if node.level else name
            yield base, node.lineno
            for alias in node.names:
                yield f"{base}.{alias.name}", node.lineno


def test_module_layers_and_no_cycles():
    files = list(MODULES.rglob("*.py"))
    modules = {
        "backend.modules." + ".".join(path.relative_to(MODULES).with_suffix("").parts): path for path in files
    }
    graph = {name: set() for name in modules}
    errors = []
    for name, path in modules.items():
        parts = path.relative_to(MODULES).parts
        owner = parts[0]
        layer = path.stem
        for dependency, line in imports(path):
            target = dependency.split(".")
            location = f"{path.relative_to(MODULES)}:{line}"
            if dependency.startswith("backend.modules.") and len(target) > 3:
                if target[2] != owner and target[3] != "public":
                    errors.append(f"{location} 不得访问其他模块私有实现: {dependency}")
            if layer == "controller" and (
                dependency.startswith(("sqlalchemy", "backend.integrations"))
                or any(part in target for part in ("dao", "entity"))
            ):
                errors.append(f"{location} Controller不得访问SQL、DAO或外部适配器")
            if layer == "service" and dependency == "sqlalchemy":
                errors.append(f"{location} SQL构造应移入DAO，Service仅管理事务")
            if layer in ("dao", "mapper", "entity") and (
                dependency.startswith(("fastapi", "httpx", "backend.integrations"))
                or "service" in target
                or "controller" in target
            ):
                errors.append(f"{location} 数据层/转换层不得反向调用业务或HTTP层")
            if dependency in graph:
                graph[name].add(dependency)
    assert not errors, "\n".join(sorted(set(errors)))

    visited, visiting = set(), []

    def visit(name):
        assert name not in visiting, "模块循环依赖: " + " -> ".join([*visiting, name])
        if name in visited:
            return
        visiting.append(name)
        for dependency in graph[name]:
            visit(dependency)
        visiting.pop()
        visited.add(name)

    for name in graph:
        visit(name)
