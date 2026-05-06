"""Skill 动态加载器"""
import importlib
import logging
import os

logger = logging.getLogger(__name__)


def load_all_skills() -> dict:
    """从 /skills 目录动态加载所有 skill"""
    skills = {}
    skills_dir = "/skills"

    if not os.path.isdir(skills_dir):
        logger.info("No /skills directory, skipping skill loading")
        return skills

    for name in os.listdir(skills_dir):
        skill_path = os.path.join(skills_dir, name)
        if os.path.isdir(skill_path) and os.path.exists(os.path.join(skill_path, "__init__.py")):
            try:
                module = importlib.import_module(f"skills.{name}")
                if hasattr(module, "Skill"):
                    skills[name] = module.Skill()
                    logger.info(f"✅ Loaded skill: {name}")
            except Exception as e:
                logger.warning(f"Failed to load skill {name}: {e}")

    return skills
