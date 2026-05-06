"""Code skill — ephemeral BaseSandbox demo.

For pooled lifecycle use AgentScope ``SandboxManager`` (see ``infra/agentscope_sandbox_service.py``).
"""
from runtime.skill.registry import BaseSkill


class Skill(BaseSkill):
    name = "code"
    description = "代码执行工具"

    def can_handle(self, text: str) -> bool:
        return "执行代码" in text or "运行代码" in text

    def execute(self, text: str) -> str:
        try:
            from agentscope_runtime.sandbox import BaseSandbox
            with BaseSandbox() as box:
                result = box.run_ipython_cell(text)
                if isinstance(result, dict) and "content" in result:
                    outputs = [c["text"] for c in result["content"] if c.get("type") == "text"]
                    return "".join(outputs)
                return str(result)
        except Exception as e:
            return f"[Code Error] {e}"
