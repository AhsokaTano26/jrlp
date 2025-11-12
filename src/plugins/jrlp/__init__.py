import random
from datetime import datetime, date
from typing import Tuple, Dict, Any

from nonebot import on_command
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.log import logger

# 存储每日匹配结果的缓存。
# 键为 (群号: int, 用户ID: int)，值为 (匹配老婆ID: int, 匹配日期: date)
# date 只记录日期部分，用于判断是否跨日
DAILY_MATCH_CACHE: Dict[Tuple[int, int], Tuple[int, date]] = {}

# 匹配命令的匹配器
jrlp_matcher = on_command(
    "jrlp",
    aliases={"今日老婆", "jrrp", "jrps"},
    priority=5,
    block=True  # 阻止事件向下传递
)


@jrlp_matcher.handle()
async def handle_jrlp(bot: Bot, event: GroupMessageEvent):
    """
    处理 jrlp 命令，检查缓存或执行新的随机匹配。
    """
    if not event.group_id:
        await jrlp_matcher.finish("这个命令只能在群聊中使用哦！")

    group_id = event.group_id
    user_id = event.user_id
    cache_key = (group_id, user_id)
    current_date = date.today()

    # --- 1. 检查缓存 ---
    current_match_data = DAILY_MATCH_CACHE.get(cache_key)

    if current_match_data:
        matched_user_id, match_date = current_match_data

        # 判断匹配日期是否在今天
        if match_date == current_date:
            # 未过期，使用缓存结果
            logger.info(f"缓存命中: 群{group_id}的用户{user_id}今天已匹配老婆{matched_user_id}")
            return await send_match_message(bot, group_id, user_id, matched_user_id)
        else:
            # 已过期（跨日），清除旧缓存
            DAILY_MATCH_CACHE.pop(cache_key)
            logger.info(f"缓存过期: 群{group_id}的用户{user_id}的匹配已清除")

    # --- 2. 获取群成员列表 ---
    try:
        # 调用 OneBot V11 接口 get_group_member_list
        member_list: list[Dict[str, Any]] = await bot.get_group_member_list(group_id=group_id)
    except Exception as e:
        logger.error(f"获取群成员列表失败: {e}")
        await jrlp_matcher.finish("获取群成员列表失败，请检查机器人的权限。")
        return

    # --- 3. 过滤并随机选择 ---
    # 过滤掉机器人账号和发起命令的自己
    valid_members = [
        member for member in member_list
        if member["user_id"] != bot.self_id and member["user_id"] != user_id
    ]

    if not valid_members:
        await jrlp_matcher.finish("群里没有其他成员可以匹配了呢！")
        return

    # 随机选择一个成员
    matched_member = random.choice(valid_members)
    matched_user_id = matched_member["user_id"]

    # --- 4. 更新缓存 ---
    DAILY_MATCH_CACHE[cache_key] = (matched_user_id, current_date)
    logger.info(f"新匹配成功: 群{group_id}的用户{user_id}匹配老婆{matched_user_id}")

    # --- 5. 发送消息 ---
    await send_match_message(bot, group_id, user_id, matched_user_id)


async def send_match_message(bot: Bot, group_id: int, request_user_id: int, matched_user_id: int):
    """
    根据匹配到的用户ID，构造并发送包含 @、文字和头像图片的组合消息。
    """
    try:
        # 获取匹配成员的详细信息（用于获取群昵称 card）
        member_info: Dict[str, Any] = await bot.get_group_member_info(
            group_id=group_id, user_id=matched_user_id, no_cache=True
        )
    except Exception as e:
        logger.error(f"获取匹配成员信息失败: {e}")
        # 如果获取信息失败，至少尝试发送文字消息
        await bot.send_group_msg(group_id=group_id,
                                 message=f"{MessageSegment.at(request_user_id)} 匹配成功，但获取老婆信息失败。")
        return

    # 优先使用群昵称 (card)，其次使用 QQ 昵称 (nickname)
    display_name = member_info.get("card") or member_info.get("nickname", "未知成员")

    # 1. @ 消息段：@发送命令的用户
    at_segment = MessageSegment.at(request_user_id)

    # 2. 文字部分：匹配结果
    text_message = Message(f"你今日的群友老婆是：{display_name}")

    # 3. 图片部分：匹配老婆的头像
    # NapCat/OneBot V11 通用的 QQ 头像 URL 格式
    avatar_url = f"http://q1.qlogo.cn/g?b=qq&nk={matched_user_id}&s=640"
    image_segment = MessageSegment.image(avatar_url)

    # 构建组合消息：@ + 文字 + 图片
    # 注意：@ 必须在最前面才能成功提及用户。
    full_message = at_segment + text_message + image_segment

    # 发送消息
    try:
        await bot.send_group_msg(group_id=group_id, message=full_message)
    except Exception as e:
        logger.error(f"发送最终消息失败: {e}")
        # 失败时发送一个纯文字的备用消息
        await bot.send_group_msg(
            group_id=group_id,
            message=f"{MessageSegment.at(request_user_id)} 匹配成功！你今日的老婆是：{display_name} (图片发送失败)"
        )

# --- 提示：关于持久化 ---
# 警告：上面的 DAILY_MATCH_CACHE 是内存存储，重启程序后匹配关系会丢失。
# 推荐使用 nonebot-plugin-datastore 或 Redis 实现真正的一天内不变。