"""部门树计算：同步范围的下级部门、成员继承上级部门的默认角色。"""


def subtree(roots, parent_of):
    """roots 及其全部下级部门；parent_of 为 {部门: 上级部门}。"""
    children = {}
    for department, parent in parent_of.items():
        children.setdefault(parent, []).append(department)
    found, stack = set(), [root for root in roots if root in parent_of]
    while stack:
        department = stack.pop()
        if department in found:
            continue
        found.add(department)
        stack.extend(children.get(department, []))
    return found


def ancestors(department, parent_of):
    """部门本身及其全部上级（防环）。"""
    chain = []
    while department in parent_of and department not in chain:
        chain.append(department)
        department = parent_of[department]
    return chain
