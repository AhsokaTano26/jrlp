import random
from datetime import datetime, time, timedelta

from nonebot import on_command, get_plugin_config
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.log import logger
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="jrlp",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

# 持久化存储，键为 (群号, 用户ID)，值为 (老婆ID, 匹配时间)
# 这里使用内存字典作为演示，实际生产环境建议使用 Redis 或数据库
DAILY_MATCH_CACHE = {}

# 匹配命令
jrlp_matcher = on_command("jrlp", priority=10)


@jrlp_matcher.handle()
async def handle_jrlp(bot: Bot, event: GroupMessageEvent):
    # 1. 检查是否为群消息
    if not event.group_id:
        await jrlp_matcher.finish("这个命令只能在群聊中使用哦！")

    group_id = event.group_id
    user_id = event.user_id
    cache_key = (group_id, user_id)

    # 2. 检查缓存，是否已匹配
    current_match_data = DAILY_MATCH_CACHE.get(cache_key)
    if current_match_data:
        matched_user_id, match_time = current_match_data

        # 检查是否过期（简单判断：匹配时间是否在今天）
        # 更严谨的方式是检查时间戳是否超过24小时或是否跨越了凌晨
        if match_time.date() == datetime.now().date():
            # 未过期，直接使用缓存结果
            logger.info(f"缓存命中: 群{group_id}的用户{user_id}已匹配老婆{matched_user_id}")
            # 跳到发送消息部分
            return await send_match_message(bot, group_id, matched_user_id)
        else:
            # 已过期，清除缓存
            DAILY_MATCH_CACHE.pop(cache_key)
            logger.info(f"缓存过期: 群{group_id}的用户{user_id}的匹配已清除")

    # 3. 获取群成员列表
    try:
        # 调用 OneBot V11 接口 get_group_member_list 获取所有群成员信息
        member_list = await bot.get_group_member_list(group_id=group_id)
    except Exception as e:
        logger.error(f"获取群成员列表失败: {e}")
        await jrlp_matcher.finish("获取群成员列表失败，请检查机器人的权限。")
        return

    # 4. 过滤机器人/自己，并随机选择
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

    # 5. 更新缓存
    DAILY_MATCH_CACHE[cache_key] = (matched_user_id, datetime.now())
    logger.info(f"新匹配成功: 群{group_id}的用户{user_id}匹配老婆{matched_user_id}")

    # 6. 发送消息
    await send_match_message(bot, user_id, group_id, matched_user_id)


async def send_match_message(bot: Bot, user_id: int, group_id: int, matched_user_id: int):
    """
    根据匹配到的用户ID，获取其信息并发送组合消息。
    """
    try:
        # 获取匹配成员的详细信息（头像、群昵称）
        member_info = await bot.get_group_member_info(
            group_id=group_id, user_id=matched_user_id, no_cache=True
        )
    except Exception as e:
        logger.error(f"获取匹配成员信息失败: {e}")
        return

    at_segment = MessageSegment.at(user_id)

    # 优先使用群昵称 (card)，其次使用 QQ 昵称 (nickname)
    display_name = member_info.get("card") or member_info.get("nickname", "未知成员")

    # 构造消息
    # OneBot V11 的头像 URL 格式通常是: http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640 (s=640 是大图尺寸)
    avatar_url = f"http://q1.qlogo.cn/g?b=qq&nk={matched_user_id}&s=640"

    # 消息的文字部分
    text_message = Message(f"你今日的群友老婆是：{display_name}")

    # 消息的图片部分
    # NapCat 依赖 OneBot V11 的 `image` 消息段，可以接受 url
    #
    image_segment = MessageSegment.image(avatar_url)

    # 构建组合消息 (注意：这里的组合方式可能因不同的 OneBot 实现和 nonebot adapter 版本略有不同)
    # 简单实现：文字 + 图片 (QQ 可能会将图片放在文字后面)
    full_message = at_segment + text_message + image_segment

    # 发送消息
    try:
        await bot.send_group_msg(group_id=group_id, message=full_message)
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        await bot.send_group_msg(group_id=group_id, message=f"匹配成功，但发送图片失败：{display_name}")