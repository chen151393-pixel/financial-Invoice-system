"""静态检查模块依赖，阻止新增代码越层或形成循环依赖。"""

import ast
import importlib.util
from pathlib import Path

MODULES = Path(__file__).resolve().parents[1] / "modules"
# 后端规则第 4 节：新模块按层分目录；旧模块仍以文件名表示层。
LAYERS = {"controller", "service", "dao", "entity", "dto", "vo", "mapper", "policy"}


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
        layer = parts[1] if len(parts) > 2 and parts[1] in LAYERS else path.stem
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
            if layer == "policy" and (
                dependency.startswith(("sqlalchemy", "fastapi", "httpx", "backend.integrations"))
                or any(part in target for part in ("dao", "service", "controller"))
            ):
                errors.append(f"{location} 规则层须为纯函数，不得访问数据库、外部系统或业务层")
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


def test_core_and_integrations_do_not_depend_on_business_modules():
    """后端规则第 2 节：core/ 与 integrations/ 不能导入业务模块或旧迁移链。"""
    backend = MODULES.parent
    errors = []
    for folder in ("core", "integrations"):
        for path in (backend / folder).rglob("*.py"):
            package = "backend." + ".".join(path.relative_to(backend).with_suffix("").parts[:-1])
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    name = "." * node.level + (node.module or "")
                    names = [importlib.util.resolve_name(name, package) if node.level else name]
                else:
                    continue
                for dependency in names:
                    if dependency.startswith(("backend.modules", "backend.legacy_migrations")):
                        errors.append(f"{path.relative_to(backend)}:{node.lineno} 不得依赖 {dependency}")
    assert not errors, "\n".join(sorted(errors))
