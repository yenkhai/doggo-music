# bot.py
import discord
import os
from dotenv import load_dotenv
import yt_dlp
import asyncio
import re
import random

# 1. 加载 .env 文件中的 Token
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# 2. 设置机器人意图
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

# 3. 初始化机器人
bot = discord.Client(intents=intents) 

# --- 全局变量 ---
song_queue = []
current_song_info = None
loop_mode = 0  # 0=关闭, 1=列表循环

# --- 智能 FFmpeg 路径设置 ---
if os.name == 'nt':
    # Windows: 请确保路径正确
    FFMPEG_EXECUTABLE_PATH = r"C:\Users\Admin\Desktop\DoggoMusic\ffmpeg-full_build\bin\ffmpeg.exe"
else:
    # Linux/Server
    FFMPEG_EXECUTABLE_PATH = 'ffmpeg'

# 4. 机器人上线事件
@bot.event
async def on_ready():
    print(f'🥳 机器人 {bot.user} 已成功登录并上线！')

# 5. 消息/命令处理中心
@bot.event
async def on_message(message):
    global song_queue, loop_mode
    
    if message.author == bot.user:
        return
    
    # --- !play (播放/排队) ---
    if message.content.startswith('!play'):
        search_query = message.content[len('!play'):].strip()
        if not search_query:
            await message.channel.send("请在 `!play` 后面输入歌曲名称或链接。")
            return
        
        await message.channel.send(f"🔍 收到请求，处理中...")
        await handle_play_command(message, search_query)

    # --- !stop (停止并清空) ---
    elif message.content.startswith('!stop'):
        if message.guild.voice_client:
            song_queue.clear()
            loop_mode = 0
            message.guild.voice_client.stop()
            await message.guild.voice_client.disconnect()
            await message.channel.send("🛑 已停止播放，清空队列并断开连接。")
        else:
            await message.channel.send("机器人当前没有连接到任何语音频道。")

    # --- !skip (跳过当前) ---
    elif message.content.startswith('!skip'):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            message.guild.voice_client.stop() 
            await message.channel.send("⏭️ 已跳过当前歌曲！")
        else:
            await message.channel.send("当前没有正在播放的音乐。")

    # --- !queue (查看队列) ---
    elif message.content.startswith('!queue'):
        if not song_queue:
            status = "📭 当前播放队列为空。"
        else:
            status = "📋 **待播放队列:**\n"
            for i, (m, u, title) in enumerate(song_queue[:10]):
                status += f"**{i+1}.** {title}\n"
            if len(song_queue) > 10:
                status += f"... 还有 {len(song_queue)-10} 首"
        
        # 显示当前循环状态
        modes = ["❌ 关闭", "🔁 列表循环"]
        status += f"\n**循环模式:** {modes[loop_mode]}"
        
        await message.channel.send(status)

    # --- !loop (切换循环模式) ---
    elif message.content.startswith('!loop'):
        loop_mode = (loop_mode + 1) % 2 
        modes = ["❌ 循环已关闭", "🔁 列表循环开启"]
        await message.channel.send(f"{modes[loop_mode]}")

    # --- !shuffle (随机播放) ---
    elif message.content.startswith('!shuffle'):
        if len(song_queue) < 2:
            await message.channel.send("队列里的歌太少，没法随机。")
        else:
            random.shuffle(song_queue)
            await message.channel.send("🔀 队列已打乱！")

    # --- !remove (移除歌曲) ---
    elif message.content.startswith('!remove'):
        try:
            index = int(message.content[len('!remove'):].strip()) - 1
            if 0 <= index < len(song_queue):
                removed_song = song_queue.pop(index)
                await message.channel.send(f"🗑️ 已从队列移除: **{removed_song[2]}**")
            else:
                await message.channel.send("找不到这首歌，请检查 !queue 的编号。")
        except:
            await message.channel.send("请输入正确的格式，例如: `!remove 1`")

    # --- !pause / !resume ---
    elif message.content.startswith('!pause'):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            message.guild.voice_client.pause()
            await message.channel.send("⏸️ 音乐已暂停。")
            
    elif message.content.startswith('!resume'):
        if message.guild.voice_client and message.guild.voice_client.is_paused():
            message.guild.voice_client.resume()
            await message.channel.send("▶️ 音乐继续播放。")

# 6. 处理搜索和URL识别逻辑
async def handle_play_command(message, query):
    YOUTUBE_URL_REGEX = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=|embed\/|v\/)?([a-zA-Z0-9_-]+)"
    
    if not message.author.voice or not message.author.voice.channel:
        await message.channel.send("您必须先加入一个语音频道！")
        return

    is_url = re.match(YOUTUBE_URL_REGEX, query)
    
    # 情况 1: 输入的是 URL
    if is_url:
        video_id = is_url.group(1)
        final_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # 获取标题
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL({'quiet':True, 'extract_flat':True}).extract_info(final_url, download=False))
            video_title = data.get('title', '未知歌曲')
        except:
            video_title = "未知 YouTube 歌曲"

        await message.channel.send(f"🔗 链接识别: **{video_title}**")
        return await play_song(message, final_url, title=video_title)
        
    # 情况 2: 输入的是关键词 (搜索)
    else:
        YDL_SEARCH_OPTIONS = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extract_flat': 'in_playlist',
            'default_search': 'ytsearch5', 
        }

        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YDL_SEARCH_OPTIONS).extract_info(query, download=False))
            results = data.get('entries', [])
            if not results:
                return await message.channel.send("未找到任何结果。")

            search_list = []
            for i, video in enumerate(results[:5]):
                title = video.get('title', '未知标题')
                search_list.append(f"**{i+1}.** {title}")

            await message.channel.send("请回复编号 (1-5)，30秒自动取消：\n\n" + "\n".join(search_list))

        except Exception as e:
            return await message.channel.send(f"搜索错误: {e}")
        
        def check(m):
            return (m.author == message.author and 
                    m.channel == message.channel and 
                    m.content.isdigit() and 
                    1 <= int(m.content) <= len(results))

        try:
            selection_message = await bot.wait_for('message', check=check, timeout=30.0)
            selected_index = int(selection_message.content) - 1
            selected_video = results[selected_index]
            
            # --- 修正点：直接使用 url 字段，绝不回退到 webpage_url ---
            final_url = selected_video.get('url')
            # 如果真的没有 url，那宁愿报错也不能给脏链接，所以这里不再写 fallback

            video_title = selected_video.get('title', '未知歌曲')
            await message.channel.send(f"✅ 已选择 **{video_title}**")
            await play_song(message, final_url, title=video_title)

        except asyncio.TimeoutError:
            await message.channel.send("超时取消。")
        except Exception as e:
            await message.channel.send(f"选择错误: {e}")

# 7. 核心播放函数
async def play_song(message, url, title="未知歌曲"):
    global song_queue, current_song_info
    
    voice_client = message.guild.voice_client
    if not voice_client:
        try:
            voice_client = await message.author.voice.channel.connect()
        except Exception as e:
            return await message.channel.send(f"连接语音失败: {e}")
            
    # 如果正在播放，加入队列
    if voice_client.is_playing():
        song_queue.append((message, url, title))
        await message.channel.send(f"📝 **{title}** 已加入队列 (位置: {len(song_queue)})")
        return

    # 更新当前播放信息
    current_song_info = (message, url, title)

    # 提取流链接
    loop = asyncio.get_event_loop()
    YDL_PLAY_OPTIONS = {
        'format': 'bestaudio/best', 
        'noplaylist': True,
        'quiet': True,
        'force_ipv4': True,
        'default_search': 'auto',
        'no_warnings': True,
    }
    
    try:
        data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YDL_PLAY_OPTIONS).extract_info(url, download=False))
        
        stream_url = None
        if 'entries' in data: data = data['entries'][0]
        
        # 1. 优先找直接的 url
        stream_url = data.get('url')
        
        # 2. 如果没有，在 formats 里找
        if not stream_url and data.get('formats'):
            for f in data['formats']:
                if f.get('url') and f.get('acodec') != 'none':
                    stream_url = f['url']
                    break
        
        # --- 修正点：删除了 data.get('webpage_url') 的回退 ---
        # 如果没有找到流媒体链接，就抛出异常，而不是用网页链接去糊弄 FFmpeg
        
        if not stream_url: raise Exception("无法提取有效流媒体链接")

    except Exception as e:
        print(f"提取失败: {e}")
        return await message.channel.send(f"播放准备失败: {e}")

    # 播放
    try:
        FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        
        audio_source = discord.FFmpegOpusAudio(stream_url, **FFMPEG_OPTIONS, executable=FFMPEG_EXECUTABLE_PATH)
        
        def after_playing(error):
            if error: print(f"播放错误: {error}")
            
            # --- 列表循环逻辑 ---
            if loop_mode == 1:
                song_queue.append(current_song_info)
            
            # --- 播放下一首逻辑 ---
            if len(song_queue) > 0:
                next_msg, next_url, next_title = song_queue.pop(0)
                coro = play_song(next_msg, next_url, next_title)
                future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            else:
                # --- 队列空了：触发自动断开倒计时 ---
                coro = auto_disconnect(voice_client)
                asyncio.run_coroutine_threadsafe(coro, bot.loop)

        voice_client.play(audio_source, after=after_playing)
        await message.channel.send(f"🎶 正在播放: **{title}**")

    except Exception as e:
        await message.channel.send(f"播放错误: {e}")

# 自动断开连接 (等待 120 秒 / 2分钟)
async def auto_disconnect(voice_client):
    await asyncio.sleep(120) 
    if voice_client.is_connected() and not voice_client.is_playing() and len(song_queue) == 0:
        await voice_client.disconnect()
        print("🤖 闲置超时(2分钟)，已自动断开。")

# 8. 启动
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
else:
    print("错误：未找到 Token")
