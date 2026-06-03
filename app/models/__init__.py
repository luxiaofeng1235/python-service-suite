"""
============================================
ORM 数据模型模块
============================================
SQLAlchemy 数据库表映射模型。
Pydantic 请求/响应模型见 app.schemas。
"""

from app.models.user import User  # noqa: F401
from app.models.user_token import UserToken  # noqa: F401
from app.models.verification_code import VerificationCode  # noqa: F401
from app.models.ai_chat_log import AiChatLog  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.auth_permission import Permission  # noqa: F401
from app.models.auth_casbin_rule import CasbinRule  # noqa: F401
from app.models.auth_role import Role  # noqa: F401
from app.models.auth_admin import AuthAdmin  # noqa: F401
from app.models.admin_token import AdminToken  # noqa: F401
from app.models.lottery_config import LotteryConfig  # noqa: F401
from app.models.lottery_record import LotteryRecord  # noqa: F401
