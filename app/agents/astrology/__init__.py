"""
============================================
Astrology Agent Package - Agent construction
============================================
Exposes the astrology execution definition independently of HTTP controllers.
"""

from app.agents.astrology.agent import create_astrology_agent

__all__ = ["create_astrology_agent"]
