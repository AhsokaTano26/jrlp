from datetime import date
from sqlalchemy import select, delete
from nonebot_plugin_orm import async_scoped_session
from .models import JrlpContent  # 确保文件名对得上

async def get_today_wife(session: async_scoped_session, group_id: int, user_id: int) -> int:
    """查询今日已匹配的老婆 ID"""
    today = str(date.today())
    stmt = select(JrlpContent.wife_id).where(
        JrlpContent.group_id == group_id,
        JrlpContent.user_id == user_id,
        JrlpContent.match_date == today
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def update_wife_relation(session: async_scoped_session, group_id: int, user_id: int, wife_id: int):
    """更新或插入匹配关系"""
    today = str(date.today())
    # 使用 merge 处理 插入/更新 逻辑
    new_record = JrlpContent(
        group_id=group_id,
        user_id=user_id,
        wife_id=wife_id,
        match_date=today
    )
    await session.merge(new_record)
    await session.commit()

async def remove_wife_relation(session: async_scoped_session, group_id: int, user_id: int):
    """删除匹配关系（抢夺成功后原关系断开）"""
    stmt = delete(JrlpContent).where(
        JrlpContent.group_id == group_id,
        JrlpContent.user_id == user_id
    )
    await session.execute(stmt)
    await session.commit()