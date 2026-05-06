"""Skill 注册基类"""


class BaseSkill:
    """所有 Skill 继承此类"""

    name: str = "base"
    description: str = ""

    def can_handle(self, text: str) -> bool:
        return False

    def execute(self, text: str) -> str:
        raise NotImplementedError
