"""Browser Skill — 沙箱内浏览器操作"""
from runtime.skill.registry import BaseSkill


class Skill(BaseSkill):
    name = "browser"
    description = "网页浏览工具"

    def can_handle(self, text: str) -> bool:
        return "打开网页" in text or "浏览" in text

    def execute(self, text: str) -> str:
        try:
            from agentscope_runtime.sandbox import BrowserSandbox
            with BrowserSandbox() as box:
                # 简单实现
                return f"[Browser] 浏览器沙箱已启动（功能待接入）"
        except Exception as e:
            return f"[Browser Error] {e}"
