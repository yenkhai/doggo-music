# bot.py
import discord
import os
from dotenv import load_dotenv
import yt_dlp       # 新增：用于搜索和获取音频流
import asyncio      # 新增：用于等待用户选择
import re           # 新增：用于处理正则表达式


# ----------------------------------------------------
# 1. 加载 .env 文件中的 Token
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ----------------------------------------------------
# 2. 设置机器人意图 (Intents)
# 意图必须与您在 Discord 开发者门户中启用的意图相匹配！
intents = discord.Intents.default()
# 启用我们需要的意图：
intents.message_content = True  # 消息内容意图 (读取 !play 后面的内容)
intents.voice_states = True     # 语音状态意图 (处理用户加入/离开语音频道)
intents.guilds = True           # 服务器信息意图 (获取频道和成员信息)

# ----------------------------------------------------
# 3. 初始化机器人客户端
# command_prefix='!' 表示您将使用 !play, !join 这样的命令
bot = discord.Client(intents=intents) 

# yt-dlp 配置
YDL_OPTIONS = {
    'format': 'bestaudio/best',        # 仅获取最佳音频格式
    'noplaylist': True,                # 禁用播放列表下载
    'quiet': True,                     # 减少控制台输出
    'extract_flat': 'in_playlist',     # 仅提取轻量级元数据
    'default_search': 'ytsearch5',     # 默认进行 YouTube 搜索，并限制结果为 5 个 (关键！)
    'ffmpeg_location': 'ffmpeg',       # 告诉 yt-dlp ffmpeg 的位置，由于已添加到 PATH，此处写 'ffmpeg' 即可
}

# --- 新增：全局歌曲队列 ---
song_queue = []


# ----------------------------------------------------
# 4. 机器人事件处理：当机器人准备好时
@bot.event
async def on_ready():
    """机器人成功连接到 Discord 时运行"""
    print(f'🥳 机器人 {bot.user} 已成功登录并上线！')
    print('现在，在您的 Discord 服务器中尝试输入 !play test_song')


# ----------------------------------------------------
# 5. 命令处理框架 (使用 Client 而非 Commands 框架的简单实现)
# 注意：对于复杂功能，建议使用 discord.ext.commands.Bot
@bot.event
async def on_message(message):
    """处理收到的所有消息"""
    
    # 忽略机器人自己的消息
    if message.author == bot.user:
        return
    
    # --- 1. 处理 !play 命令 ---
    if message.content.startswith('!play'):
        # 提取用户想搜索的关键词
        search_query = message.content[len('!play'):].strip()
        
        if not search_query:
            await message.channel.send("请在 `!play` 后面输入您想播放的歌曲名称或链接。")
            return
            
        await message.channel.send(f"收到播放请求: **{search_query}**。正在搜索... 🔍")
        await handle_play_command(message, search_query)

    # --- 2. 处理 !stop 命令 (停止并断开) ---
    elif message.content.startswith('!stop'):
        if message.guild.voice_client:
            # 关键修改：停止时先清空队列，防止机器人自动播放下一首
            global song_queue
            song_queue.clear()
            
            message.guild.voice_client.stop()
            await message.guild.voice_client.disconnect()
            await message.channel.send("🛑 已停止播放，清空队列并断开连接。")
        else:
            await message.channel.send("机器人当前没有连接到任何语音频道。")

    # --- 3. 处理 !skip 命令 (跳过当前歌曲) ---
    elif message.content.startswith('!skip'):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            # stop() 会触发 play_song 里的 after 回调，
            # 回调函数会自动检查队列并播放下一首，从而实现“跳过”效果
            message.guild.voice_client.stop()
            await message.channel.send("⏭️ 已跳过当前歌曲！")
        else:
            await message.channel.send("当前没有正在播放的音乐。")

    # --- 4. 处理 !queue 命令 (查看播放列表) ---
    elif message.content.startswith('!queue'):
        if not song_queue:
            await message.channel.send("📭 当前播放队列为空。")
        else:
            queue_list = "📋 **待播放队列:**\n"
            # 遍历队列，显示前 10 首，避免消息太长
            for i, (m, u, title) in enumerate(song_queue[:10]):
                queue_list += f"**{i+1}.** {title}\n"
            
            if len(song_queue) > 10:
                queue_list += f"... 还有 {len(song_queue)-10} 首"
                
            await message.channel.send(queue_list)
            
    # --- 5. 处理 !pause 和 !resume (暂停/继续) ---
    elif message.content.startswith('!pause'):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            message.guild.voice_client.pause()
            await message.channel.send("⏸️ 音乐已暂停。")
            
    elif message.content.startswith('!resume'):
        if message.guild.voice_client and message.guild.voice_client.is_paused():
            message.guild.voice_client.resume()
            await message.channel.send("▶️ 音乐继续播放。")


# ----------------------------------------------------
# 6. 主要播放/搜索逻辑的占位符函数
# 核心播放/搜索逻辑
# 核心播放/搜索逻辑 - 修复版
async def handle_play_command(message, query):
    """处理音乐播放逻辑：区分 URL 和搜索词，然后执行搜索/播放"""

    # YouTube URL 正则表达式，用于判断用户输入是否为链接
    YOUTUBE_URL_REGEX = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=|embed\/|v\/)?([a-zA-Z0-9_-]+)"
    
    # 检查用户是否在语音频道中
    if not message.author.voice or not message.author.voice.channel:
        await message.channel.send("您必须先加入一个语音频道才能播放音乐！")
        return

    is_url = re.match(YOUTUBE_URL_REGEX, query)
    
    # --- 情况 1: 用户输入的是 URL ---
    if is_url:
        video_id = is_url.group(1)
        final_url = f"https://www.youtube.com/watch?v={video_id}" # 构造干净的 URL
        await message.channel.send(f"检测到有效的 YouTube 链接，正在连接语音频道...")
        # 传入 title 参数 (URL模式暂时不知道标题，先写 'URL歌曲') 之后可以尝试获取歌名
        return await play_song(message, final_url,title="URL 点歌")
        
    # --- 情况 2: 用户输入的是搜索词 (只有在这个 else 块中执行搜索和选择) ---
    else:
        YDL_SEARCH_OPTIONS = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extract_flat': 'in_playlist',
            'default_search': 'ytsearch5', 
        }

        await message.channel.send(f"正在搜索 **{query}**，请稍候...")
        
        loop = asyncio.get_event_loop()

        try:
            # B. 使用 yt-dlp 搜索 Top 5 结果
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YDL_SEARCH_OPTIONS).extract_info(query, download=False))

            results = data.get('entries', [])
            if not results:
                return await message.channel.send("未找到任何结果。")

            # 构造选择列表
            search_list = []
            for i, video in enumerate(results[:5]):
                title = video.get('title', '未知标题')
                search_list.append(f"**{i+1}.** {title}")

            list_message = "请回复您要播放的歌曲编号 (1-5)，30 秒后将自动取消：\n\n" + "\n".join(search_list)
            await message.channel.send(list_message)

        except Exception as e:
            await message.channel.send(f"搜索发生错误: {e}")
            return
        
        # C. 等待用户选择
        def check(m):
            # 检查：来自原用户，在原频道，且内容是 1-5 之间的数字
            return (m.author == message.author and 
                    m.channel == message.channel and 
                    m.content.isdigit() and 
                    1 <= int(m.content) <= len(results))

        try:
            # 修复 2：等待用户回复，并获取选择消息
            selection_message = await bot.wait_for('message', check=check, timeout=30.0) 
            
            selected_index = int(selection_message.content) - 1
            selected_video = results[selected_index]
            final_url = selected_video.get('url') # 获取干净 URL

            # D. 调用播放函数
            video_title = selected_video.get('title', '未知歌曲') # 获取标题
            await message.channel.send(f"已选择 **{video_title}**。处理中...")
            # 修改：传入 title 参数
            await play_song(message, final_url, title=video_title)

        except asyncio.TimeoutError:
            await message.channel.send("选择超时，操作已取消。")
        except Exception as e:
            await message.channel.send(f"处理选择时发生错误: {e}")


# bot.py 文件中，在 handle_play_command 函数的后面
async def play_song(message, url, title="未知歌曲"):
    """
    负责连接语音频道、播放歌曲、处理队列
    """
    global song_queue # 声明我们要使用全局队列变量
    
    # 1. 获取或建立语音连接
    voice_client = message.guild.voice_client
    
    if not voice_client: # 如果机器人还没进语音频道
        if not message.author.voice:
             return await message.channel.send("您必须先加入一个语音频道！")
        try:
            voice_client = await message.author.voice.channel.connect()
            await message.channel.send(f"已连接到语音频道 🎤")
        except Exception as e:
            return await message.channel.send(f"连接失败: {e}")
            
    # 2. 检查是否正在播放
    if voice_client.is_playing():
        # 如果正在播放，将歌曲信息加入队列
        song_queue.append((message, url, title))
        await message.channel.send(f"✅ **{title}** 已加入队列！(当前位置: {len(song_queue)})")
        return # 结束函数，不打断当前播放

    # 3. 提取流媒体信息 (和之前一样)
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
        
        # URL 提取逻辑 (和您之前成功的逻辑保持一致)
        stream_url = None
        if 'entries' in data: data = data['entries'][0]
        stream_url = data.get('url')
        if not stream_url and data.get('formats'):
            for f in data['formats']:
                if f.get('url') and f.get('acodec') != 'none':
                    stream_url = f['url']
                    break
        if not stream_url and data.get('webpage_url'): stream_url = data['webpage_url']
        
        if not stream_url: raise Exception("无法提取有效音频流")

    except Exception as e:
        print(f"提取失败: {e}")
        return await message.channel.send(f"播放出错: {e}")

    # 4. 开始播放 (关键：添加 after 回调)
    try:
        FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        # ⚠️ 请确保这里的路径是您之前硬编码的正确路径
        #FFMPEG_EXECUTABLE_PATH = r"C:\Users\Admin\Desktop\DoggoMusic\ffmpeg-full_build\bin\ffmpeg.exe"
        FFMPEG_EXECUTABLE_PATH = os.getenv("FFMPEG_PATH") or 'ffmpeg'
        audio_source = discord.FFmpegOpusAudio(stream_url, **FFMPEG_OPTIONS, executable=FFMPEG_EXECUTABLE_PATH)
        
        # 定义当这首歌唱完后要做什么 (检查队列)
        def after_playing(error):
            if error: print(f"播放错误: {error}")
            # 检查队列里还有没有歌
            if len(song_queue) > 0:
                # 取出下一首: (message, url, title)
                next_msg, next_url, next_title = song_queue.pop(0)
                # 因为 after_playing 不是异步函数，我们需要这样调用 play_song
                coro = play_song(next_msg, next_url, next_title)
                future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                try: future.result()
                except: pass
            else:
                # 队列空了，可以选择断开连接或者仅仅待机
                # asyncio.run_coroutine_threadsafe(voice_client.disconnect(), bot.loop) # 如果想唱完自动断开可取消注释
                pass

        # 播放并挂载回调函数
        voice_client.play(audio_source, after=after_playing)
        await message.channel.send(f"🎧 正在播放: **{title}**")

    except Exception as e:
        await message.channel.send(f"播放发生错误: {e}")
# bot.py 文件中，在 on_message(message) 函数内


# ----------------------------------------------------
# 7. 启动机器人
if DISCORD_TOKEN:
    try:
        # 运行机器人，将 Token 传递给它
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("错误：Token 无效或不正确。请检查您的 .env 文件。")
else:
    print("错误：未在 .env 文件中找到 DISCORD_TOKEN。")