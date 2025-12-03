# bot.py
import discord
import os
from dotenv import load_dotenv
import yt_dlp
import asyncio
import re
import random  # 新增：用于随机播放

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
current_song_info = None  # 新增：记录当前正在播放的歌 (用于循环)
loop_mode = 0             # 新增：0=关闭, 1=单曲循环, 2=列表循环

# --- 智能 FFmpeg 路径设置 ---
# 如果系统是 Windows (nt)，使用硬编码的本地路径
if os.name == 'nt':
    # 请确保这个路径是您电脑上ffmpeg.exe的真实路径
    FFMPEG_EXECUTABLE_PATH = r"C:\Users\Admin\Desktop\DoggoMusic\ffmpeg-full_build\bin\ffmpeg.exe"
# 否则（在服务器/Linux上），直接使用系统命令
else:
    FFMPEG_EXECUTABLE_PATH = 'ffmpeg'

# 4. 机器人上线事件
@bot.event
async def on_ready():
  print(f'🥳 Bot {bot.user} has successfully logged in and is online!')


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
            await message.channel.send("Please enter a song name or link after !play")
            return
        
        await message.channel.send(f"🔍 Received playback request: {search_query}. Searching...")
        await handle_play_command(message, search_query)

    # --- !stop (停止并清空) ---
    elif message.content.startswith('!stop'):
        if message.guild.voice_client:
            song_queue.clear() # 清空队列
            loop_mode = 0      # 重置循环模式
            message.guild.voice_client.stop()
            await message.guild.voice_client.disconnect()
            await message.channel.send("🛑 Stopped playing, cleared the queue, and disconnected.")
        else:
            await message.channel.send("The bot is currently not connected to any voice channel.")

    # --- !skip (跳过当前) ---
    elif message.content.startswith('!skip'):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            # 如果是单曲循环模式，跳过时临时关掉循环，否则会跳不出去
            if loop_mode == 1:
                await message.channel.send("⏭️ 跳过当前（单曲循环暂停一次）...")
                # 这里我们在 after_playing 里处理逻辑，不用改 loop_mode 变量，
                # 只需要强制停止，逻辑会进入下一首
            else:
                await message.channel.send("⏭️ 已跳过当前歌曲！")
            
            message.guild.voice_client.stop() 
        else:
            await message.channel.send("当前没有正在播放的音乐。")

    # --- !queue (查看队列) ---
    elif message.content.startswith('!queue'):
        if not song_queue:
            status = "📭 Playlist is Empty。"
        else:
            status = "📋 **PlayList:**\n"
            for i, (m, u, title) in enumerate(song_queue[:10]):
                status += f"**{i+1}.** {title}\n"
            if len(song_queue) > 10:
                status += f"... 还有 {len(song_queue)-10} 首"
        
        # 显示当前循环状态
        modes = ["❌ Close", "🔂 Single Loop", "🔁 Loop The List"]
        status += f"\n**Mode:** {modes[loop_mode]}"
        
        await message.channel.send(status)

    # --- !loop (切换循环模式) [新功能] ---
    elif message.content.startswith('!loop'):
        loop_mode = (loop_mode + 1) % 3 # 在 0, 1, 2 之间切换
        modes = ["❌ Loop Close", "🔂 Single Loop On", "🔁 Loop On"]
        await message.channel.send(f"{modes[loop_mode]}")

    # --- !shuffle (随机播放) [新功能] ---
    elif message.content.startswith('!shuffle'):
        if len(song_queue) < 2:
            await message.channel.send("Lack of Song(<1)。")
        else:
            random.shuffle(song_queue)
            await message.channel.send("🔀 Everyday Iam shuffling！")

    # --- !remove (移除歌曲) [新功能] ---
    elif message.content.startswith('!remove'):
        try:
            # 获取用户输入的数字
            index = int(message.content[len('!remove'):].strip()) - 1
            if 0 <= index < len(song_queue):
                removed_song = song_queue.pop(index)
                await message.channel.send(f"🗑️ removed liao : **{removed_song[2]}**")
            else:
                await message.channel.send("Not Found，Please Check。")
        except:
            await message.channel.send("Please select correct Num，Eg: `!remove 3`")

    # --- !pause / !resume ---
    elif message.content.startswith('!pause'):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            message.guild.voice_client.pause()
            await message.channel.send("⏸️ Life stopped。")
            
    elif message.content.startswith('!resume'):
        if message.guild.voice_client and message.guild.voice_client.is_paused():
            message.guild.voice_client.resume()
            await message.channel.send("▶️ Life goes on。")

# 6. 处理搜索和URL识别逻辑
async def handle_play_command(message, query):
    YOUTUBE_URL_REGEX = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=|embed\/|v\/)?([a-zA-Z0-9_-]+)"
    
    if not message.author.voice or not message.author.voice.channel:
        await message.channel.send("You join Channel first！")
        return

    is_url = re.match(YOUTUBE_URL_REGEX, query)
    
    # 情况 1: 输入的是 URL
    if is_url:
        video_id = is_url.group(1)
        final_url = f"https://www.youtube.com/watch?v={video_id}"
        await message.channel.send(f"🔗 Detect dou youtube link ready to play ...")
        return await play_song(message, final_url, title="URL 点歌")
        
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
                return await message.channel.send("not found any result。")

            search_list = []
            for i, video in enumerate(results[:5]):
                title = video.get('title', '未知标题')
                search_list.append(f"**{i+1}.** {title}")

            await message.channel.send("Please select (1-5)，auto cancel after 30s ：\n\n" + "\n".join(search_list))

        except Exception as e:
            return await message.channel.send(f"Search Wrong: {e}")
        
        def check(m):
            return (m.author == message.author and 
                    m.channel == message.channel and 
                    m.content.isdigit() and 
                    1 <= int(m.content) <= len(results))

        try:
            selection_message = await bot.wait_for('message', check=check, timeout=30.0)
            selected_index = int(selection_message.content) - 1
            selected_video = results[selected_index]
            
            # 提取干净的 URL
            final_url = selected_video.get('url')
            if not final_url: final_url = selected_video.get('url')

            video_title = selected_video.get('title', 'Unknown Title')
            await message.channel.send(f"✅ 已选择 **{video_title}**")
            await play_song(message, final_url, title=video_title)

        except asyncio.TimeoutError:
            await message.channel.send("Timeout。")
        except Exception as e:
            await message.channel.send(f"Choose Wrong: {e}")

# 7. 核心播放函数 (含队列、循环、自动断开逻辑)
async def play_song(message, url, title="Unknown Title"):
    global song_queue, current_song_info
    
    voice_client = message.guild.voice_client
    if not voice_client:
        try:
            voice_client = await message.author.voice.channel.connect()
        except Exception as e:
            return await message.channel.send(f"Connect failed: {e}")
            
    # 如果正在播放，加入队列
    if voice_client.is_playing():
        song_queue.append((message, url, title))
        await message.channel.send(f"📝 **{title}** In Queue (place: {len(song_queue)})")
        return

    # 更新当前播放信息 (用于循环功能)
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
        stream_url = data.get('url')
        if not stream_url and data.get('formats'):
            for f in data['formats']:
                if f.get('url') and f.get('acodec') != 'none':
                    stream_url = f['url']
                    break
        if not stream_url and data.get('webpage_url'): stream_url = data['webpage_url']
        
        if not stream_url: raise Exception("无法提取有效流")

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
            
            # --- 核心循环逻辑 ---
            # 模式 1: 单曲循环
            if loop_mode == 1:
                # 重新播放当前这首
                coro = play_song(current_song_info[0], current_song_info[1], current_song_info[2])
                future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                return

            # 模式 2: 列表循环 (把刚才唱完的这首加到队尾)
            if loop_mode == 2:
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

# 新增：自动断开连接的逻辑 (等待 5 分钟)
async def auto_disconnect(voice_client):
    await asyncio.sleep(300) # 等待 300 秒 (5分钟)
    # 醒来后检查：1. 是否还在连接 2. 是否在播放 3. 队列是否为空
    if voice_client.is_connected() and not voice_client.is_playing() and len(song_queue) == 0:
        await voice_client.disconnect()
        print("🤖 Over 5 min, auto disconnect。")

# 8. 启动
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
else:
    print("错误：未找到 Token")