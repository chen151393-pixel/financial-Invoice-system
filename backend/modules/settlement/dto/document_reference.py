"""直接资料组作用域标识；与香港批次整数 ID、单票报关单字符串明确区分。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentGroupRef:
    id: int
