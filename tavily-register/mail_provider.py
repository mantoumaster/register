"""Email provider selection."""

from config import EMAIL_PROVIDER
from luckmail_provider import LuckMailProvider
from outlook_tw_provider import OutlookTwProvider


def create_mail_provider():
    provider = EMAIL_PROVIDER.strip().lower().replace("-", "_")
    if provider == "luckmail":
        return LuckMailProvider()
    if provider in {"outlook_tw", "outlooktw"}:
        return OutlookTwProvider()
    raise ValueError(
        f"不支持的 EMAIL_PROVIDER: {EMAIL_PROVIDER}，可选值: luckmail, outlook_tw"
    )
