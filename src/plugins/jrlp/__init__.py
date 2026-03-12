import random
from typing import Dict, Any
import hashlib
import time
import secrets
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

    matched_member = secrets.choice(valid_members)
    matched_user_id = matched_member["user_id"]

    # --- 4. 更新数据库 ---
    await update_wife_relation(session, group_id, user_id, matched_user_id)
    logger.info(f"新匹配成功并入库: 群{group_id}的用户{user_id}匹配老婆{matched_user_id}")

    # --- 5. 发送消息 ---
    await send_match_message(bot, group_id, user_id, matched_user_id, "你今日的群友老婆是：")


@rob_lp_matcher.handle()
async def handle_rob(bot: Bot, event: GroupMessageEvent, session: async_scoped_session):
    group_id = int(event.group_id)
    user_id = int(event.user_id)

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
        msg = "人家" + MessageSegment.at(target_id) + "还没老婆呢，你抢个空气啊！"
        await rob_lp_matcher.finish(msg)

    seed_str = f"{user_id}{int(time.time())}"
    luck_roll = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) / (16 ** 32)

    if user_id == 1049109092:
        luck_roll = 0.01
    # 2. 判定成功率
    if luck_roll < 0.15:
        await remove_wife_relation(session, group_id, target_id)
        await update_wife_relation(session, group_id, user_id, target_wife_id)
        await send_match_message(bot, group_id, user_id, target_wife_id,
                                 f"【横刀夺爱】你展现了惊人的魅力，{MessageSegment.at(target_id)} 的老婆直接跟你跑了！")

        # 情况 B：【普通成功】 (25% 概率) - 0.15 到 0.40 之间
    elif luck_roll < 0.40:
        await remove_wife_relation(session, group_id, target_id)
        await update_wife_relation(session, group_id, user_id, target_wife_id)
        await send_match_message(bot, group_id, user_id, target_wife_id, "【趁虚而入】你成功抢到了老婆：")

        # 情况 C：【两败俱伤/劫胡】 (10% 概率) - 0.40 到 0.50 之间
    elif luck_roll < 0.50:
        await remove_wife_relation(session, group_id, target_id)
        await rob_lp_matcher.finish(Message("由于场面太过混乱，") +
                                    MessageSegment.at(target_id) +
                                    Message("的老婆趁机溜走，不知去向了！") )

        # 情况 D：【惊天反转/白给】 (10% 概率) - 0.85 以上
        # 逻辑：抢夺失败，如果你自己有老婆，你的老婆反而会变成对方的
    elif luck_roll > 0.85:
        my_wife_id = await get_today_wife(session, group_id, user_id)
        if my_wife_id:
            await remove_wife_relation(session, group_id, user_id)
            await update_wife_relation(session, group_id, target_id, my_wife_id)
            await rob_lp_matcher.send(
                Message("【赔了夫人又折兵！】你抢人不成，反而把自己的老婆赔给了") +
                MessageSegment.at(target_id) +
                Message("！") )
            await send_match_message(bot, group_id, target_id, my_wife_id, "这是你意外获得的新老婆：")
        else:
            await rob_lp_matcher.finish(
                Message("你试图强抢，结果被") +
                MessageSegment.at(target_id) +
                Message("按在地上摩擦，还被围观群众嘲笑！") )

        # 情况 E：【普通失败】 (剩余 40% 概率)
    else:
        fail_msgs = [
            "对方甚至没正眼看你，抢夺失败。",
            "你还没进家门就被对方养的狗撵出来了。",
            "计划败露，你灰溜溜地逃跑了。",
            "对方的防御密不透风，你无从下手。"
        ]
        await rob_lp_matcher.finish(MessageSegment.at(user_id) +
                                    Message(random.choice(fail_msgs)) )



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