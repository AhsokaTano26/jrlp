import random
from datetime import date
from typing import Dict, Any

from nonebot import on_command
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.log import logger
# 导入 ORM 的异步 Session 注入
from nonebot_plugin_orm import async_scoped_session

# 导入你定义的方法和模型
from .models_method import get_today_wife, update_wife_relation, remove_wife_relation

# 匹配命令
jrlp_matcher = on_command("jrlp", aliases={"今日老婆", "jrrp", "jrps"}, priority=10, block=True)
# 抢老婆命令
rob_lp_matcher = on_command("抢老婆", aliases={"qlp", "强娶"}, priority=10, block=True)


@jrlp_matcher.handle()
async def handle_jrlp(bot: Bot, event: GroupMessageEvent, session: async_scoped_session):
    if not event.group_id:
        await jrlp_matcher.finish("这个命令只能在群聊中使用哦！")

    group_id = event.group_id
    user_id = event.user_id

    # --- 1. 从数据库检查今日是否已匹配 ---
    matched_user_id = await get_today_wife(session, group_id, user_id)

    if matched_user_id:
        logger.info(f"数据库命中: 群{group_id}的用户{user_id}今天已匹配老婆{matched_user_id}")
        return await send_match_message(bot, group_id, user_id, matched_user_id, "你今日的群友老婆已经是：")

    # --- 2. 获取群成员列表 ---
    try:
        member_list: list[Dict[str, Any]] = await bot.get_group_member_list(group_id=group_id)
    except Exception as e:
        logger.error(f"获取群成员列表失败: {e}")
        await jrlp_matcher.finish("获取群成员列表失败，请检查机器人的权限。")
        return

    # --- 3. 过滤并随机选择 ---
    valid_members = [
        member for member in member_list
        if member["user_id"] != bot.self_id and member["user_id"] != user_id
    ]

    if not valid_members:
        await jrlp_matcher.finish("群里没有其他成员可以匹配了呢！")
        return

    matched_member = random.choice(valid_members)
    matched_user_id = matched_member["user_id"]

    # --- 4. 更新数据库 ---
    await update_wife_relation(session, group_id, user_id, matched_user_id)
    logger.info(f"新匹配成功并入库: 群{group_id}的用户{user_id}匹配老婆{matched_user_id}")

    # --- 5. 发送消息 ---
    await send_match_message(bot, group_id, user_id, matched_user_id, "你今日的群友老婆是：")


@rob_lp_matcher.handle()
async def handle_rob(bot: Bot, event: GroupMessageEvent, session: async_scoped_session):
    group_id = event.group_id
    user_id = event.user_id

    # 提取被抢夺的目标 (@的人)
    target_id = None
    for seg in event.get_message():
        if seg.type == "at":
            target_id = int(seg.data["qq"])
            break

    if not target_id or target_id == user_id:
        await rob_lp_matcher.finish("你要抢谁的老婆？请 @ 他！")

    # 1. 检查被抢者是否有老婆
    target_wife_id = await get_today_wife(session, group_id, target_id)
    if not target_wife_id:
        await rob_lp_matcher.finish(f"人家 [at:qq={target_id}] 还没老婆呢，你抢个空气啊！")

    # 2. 判定成功率 (40% 成功率)
    if random.random() < 0.4:
        # 抢夺成功：移除原主关系，建立新关系
        await remove_wife_relation(session, group_id, target_id)
        await update_wife_relation(session, group_id, user_id, target_wife_id)

        await send_match_message(
            bot, group_id, user_id, target_wife_id,
            f"【NTR成功！】你成功从 [at:qq={target_id}] 手中抢走了老婆："
        )
    else:
        # 抢夺失败
        await rob_lp_matcher.finish(MessageSegment.at(user_id) + " 你试图强抢民女，但被对方乱棍打出了家门！")


async def send_match_message(bot: Bot, group_id: int, request_user_id: int, matched_user_id: int, title: str):
    """
    构造并发送包含 @、自定义标题文字和头像图片的组合消息。
    """
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=matched_user_id, no_cache=True)
        display_name = member_info.get("card") or member_info.get("nickname", str(matched_user_id))
    except Exception:
        display_name = str(matched_user_id)

    at_segment = MessageSegment.at(request_user_id)
    text_message = Message(f"\n{title}\n✨ {display_name} ({matched_user_id})")
    avatar_url = f"http://q1.qlogo.cn/g?b=qq&nk={matched_user_id}&s=640"
    image_segment = MessageSegment.image(avatar_url)

    full_message = at_segment + text_message + image_segment

    try:
        await bot.send_group_msg(group_id=group_id, message=full_message)
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        await bot.send_group_msg(group_id=group_id, message=f"{at_segment} 匹配成功！今日老婆是：{display_name}")