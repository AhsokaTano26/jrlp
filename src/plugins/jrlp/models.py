from nonebot_plugin_orm import Model
from sqlalchemy import Column, String, INTEGER


class JrlpContent(Model):
    __tablename__ = "JrlpContent"
    id = Column(String(255), primary_key=True, nullable=True)
    user_id = Column(INTEGER, nullable=True)
    group_id = Column(INTEGER, nullable=True)
    wife_id = Column(INTEGER, nullable=True)
    match_date = Column(String(20), nullable=False)  # 存储日期字符串 YYYY-MM-DD
