"""
============================================
邮件发送工具类 — 基于 SMTP 异步/同步发送
============================================
封装了邮件发送的所有底层逻辑，业务层直接调用即可。

使用方式：
    from app.utils.email import EmailUtil

    # 简单文本邮件
    await EmailUtil.send_text("user@example.com", "标题", "内容")

    # HTML 邮件
    await EmailUtil.send_html("user@example.com", "标题", "<h1>内容</h1>")

    # 带附件的邮件
    await EmailUtil.send_email(
        "user@example.com", "标题", "内容",
        attachments=["/path/to/file.pdf"]
    )

说明：
    - 配置从 settings（.env）读取，开箱即用
    - 支持 SSL（465）和 STARTTLS（587）两种模式
    - 自动根据端口选择加密方式
"""

from app.pkg.logging import get_logger
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from app.core.config import settings

logger = get_logger(__name__)


class EmailUtil:
    """
    邮件发送工具类

    所有方法均为 classmethod，无需实例化，直接 EmailUtil.send_xxx() 调用。

    Attributes:
        _host:      SMTP 服务器地址（如 smtp.qq.com）
        _port:      SMTP 端口（465=SSL / 587=STARTTLS / 25=明文）
        _user:      SMTP 登录用户名（通常为邮箱地址）
        _password:  SMTP 授权码（非邮箱登录密码）
        _sender:    发件人邮箱地址
        _sender_name: 发件人显示名称（如 "LS FastAPI"）
    """

    # ==================== 读取配置 ====================

    _host: str = settings.SMTP_HOST
    _port: int = settings.SMTP_PORT
    _user: str = settings.SMTP_USER
    _password: str = settings.SMTP_PASSWORD
    _sender: str = settings.SMTP_SENDER or settings.SMTP_USER
    _sender_name: str = settings.SMTP_SENDER_NAME or settings.PROJECT_NAME

    # ==================== 发送入口 ====================

    @classmethod
    async def send_text(
        cls,
        to_email: str,
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> bool:
        """
        发送纯文本邮件

        Args:
            to_email: 收件人邮箱
            subject:  邮件主题
            body:     邮件正文（纯文本）
            cc:       抄送列表

        Returns:
            是否发送成功
        """
        return await cls.send_email(to_email, subject, body, cc=cc, html=False)

    @classmethod
    async def send_html(
        cls,
        to_email: str,
        subject: str,
        html_body: str,
        cc: list[str] | None = None,
    ) -> bool:
        """
        发送 HTML 邮件

        Args:
            to_email:  收件人邮箱
            subject:   邮件主题
            html_body: 邮件正文（HTML）
            cc:        抄送列表

        Returns:
            是否发送成功
        """
        return await cls.send_email(to_email, subject, html_body, cc=cc, html=True)

    @classmethod
    async def send_email(
        cls,
        to_email: str,
        subject: str,
        body: str,
        cc: list[str] | None = None,
        html: bool = False,
        attachments: list[str] | None = None,
    ) -> bool:
        """
        通用邮件发送（核心方法）

        Args:
            to_email:    收件人邮箱
            subject:     邮件主题
            body:        邮件正文
            cc:          抄送列表
            html:        是否 HTML 格式（默认纯文本）
            attachments: 附件路径列表

        Returns:
            是否发送成功
        """
        try:
            # 构建邮件消息
            msg = cls._build_message(subject, body, html, attachments)

            # 设置发件人
            msg["From"] = formataddr((cls._sender_name, cls._sender))
            msg["To"] = to_email

            # 抄送
            all_recipients = [to_email]
            if cc:
                msg["Cc"] = ", ".join(cc)
                all_recipients.extend(cc)

            # 选择加密方式和端口
            if cls._port == 465:
                # SSL 模式
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(cls._host, cls._port, context=context) as server:
                    server.login(cls._user, cls._password)
                    server.sendmail(cls._sender, all_recipients, msg.as_string())
            else:
                # STARTTLS（587）或明文（25）
                with smtplib.SMTP(cls._host, cls._port, timeout=10) as server:
                    if cls._port == 587:
                        server.starttls()
                    server.login(cls._user, cls._password)
                    server.sendmail(cls._sender, all_recipients, msg.as_string())

            logger.info(f"✅ 邮件发送成功 -> {to_email} | 主题: {subject}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error(f"❌ SMTP 认证失败，请检查用户名/授权码: {cls._user}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP 发送异常: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 邮件发送未知错误: {e}")
            return False

    # ==================== 构建邮件内容 ====================

    @classmethod
    def _build_message(
        cls,
        subject: str,
        body: str,
        html: bool = False,
        attachments: list[str] | None = None,
    ) -> MIMEMultipart:
        """
        构建 MIME 邮件消息

        Args:
            subject:     邮件主题
            body:        邮件正文
            html:        是否 HTML
            attachments: 附件路径列表

        Returns:
            构建好的 MIMEMultipart 对象
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject

        # 正文部分
        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))

        # 附件部分
        if attachments:
            # 改用 mixed 类型以支持附件
            msg_mixed = MIMEMultipart("mixed")
            # 复制 alternative 部分
            for part in msg.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    msg_mixed.attach(part)
            # 替换 msg
            msg = msg_mixed

            for filepath in attachments:
                path = Path(filepath)
                if not path.exists():
                    logger.warning(f"⚠️ 附件不存在，跳过: {filepath}")
                    continue
                with open(path, "rb") as f:
                    attachment = MIMEApplication(f.read(), Name=path.name)
                    attachment["Content-Disposition"] = f'attachment; filename="{path.name}"'
                    msg.attach(attachment)

        return msg

    # ==================== 便捷方法：验证码邮件 ====================

    @classmethod
    async def send_verification_code_email(
        cls,
        to_email: str,
        username: str,
        code: str,
        expire_minutes: int = 30,
    ) -> bool:
        """
        发送验证码邮件（密码重置等场景）

        Args:
            to_email:       收件人邮箱
            username:       用户名（用于邮件中称呼）
            code:           6 位数字验证码
            expire_minutes: 验证码有效期（分钟）

        Returns:
            是否发送成功
        """
        subject = f"【{cls._sender_name}】密码重置验证码"

        html_body = f"""
        <div style="max-width:600px;margin:0 auto;padding:20px;font-family:'Microsoft YaHei',Arial,sans-serif;">
            <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;border-radius:10px 10px 0 0;text-align:center;">
                <h2 style="color:#fff;margin:0;font-size:22px;">🔐 密码重置</h2>
            </div>
            <div style="background:#fff;padding:30px;border:1px solid #e8e8e8;border-top:none;border-radius:0 0 10px 10px;">
                <p style="font-size:16px;color:#333;">尊敬的 <strong>{username}</strong>，您好：</p>
                <p style="font-size:14px;color:#666;line-height:1.8;">
                    您已申请密码重置，请使用以下验证码完成验证：
                </p>
                <div style="text-align:center;margin:30px 0;">
                    <div style="display:inline-block;padding:15px 50px;font-size:36px;font-weight:bold;
                                color:#667eea;background:#f0f0ff;border-radius:10px;
                                letter-spacing:8px;font-family:'Courier New',monospace;">
                        {code}
                    </div>
                </div>
                <p style="font-size:14px;color:#666;line-height:1.8;">
                    请在重置密码页面输入上方 6 位验证码。
                </p>
                <p style="font-size:14px;color:#666;line-height:1.8;">
                    ⏰ 该验证码 <strong>{expire_minutes} 分钟</strong> 内有效，请尽快完成重置。
                    <br>
                    如果您没有申请密码重置，请忽略此邮件，您的账号安全不受影响。
                </p>
                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <p style="font-size:12px;color:#bbb;text-align:center;">
                    此为系统自动发送邮件，请勿直接回复
                </p>
            </div>
        </div>
        """

        return await cls.send_html(to_email, subject, html_body)
