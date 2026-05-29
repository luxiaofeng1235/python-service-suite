"""
============================================
邮件（SMTP）配置
============================================
"""

SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465  # 465=SSL / 587=STARTTLS

SMTP_SENDER = None
SMTP_SENDER_NAME = None
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30
RESET_PASSWORD_BASE_URL = "http://localhost:3000/reset-password"
SMTP_SENDER_1= True
