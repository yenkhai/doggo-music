# bot.py
import discord
import os
from dotenv import load_dotenv
import yt_dlp
import asyncio
import re
import random

# 1. Load Token from .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# 2. Setup Intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

# 3. Initialize Bot
bot = discord.Client(intents=intents) 

# --- Global Variables ---
song_queue = []
current_song_info = None
loop_mode = 0  # 0=Off, 1=List Loop

# --- Smart FFmpeg Path ---
if os.name == 'nt':
    # Windows: Ensure this path is correct for your local machine
    FFMPEG_EXECUTABLE_PATH = r"C:\Users\Admin\Desktop\DoggoMusic\ffmpeg-full_build\bin\ffmpeg.exe"
else:
    # Linux/Server
    FFMPEG_EXECUTABLE_PATH = 'ffmpeg'

# 4. On Ready Event
@bot.event
async def on_ready():
    print(f'🥳 Bot {bot.user} is online and ready!')

# 5. Message/Command Handler
@bot.event
async def on_message(message):
    global song_queue, loop_mode
    
    if message.author == bot.user:
        return
    
    # --- !play ---
    if message.content.startswith('!play'):
        search_query = message.content[len('!play'):].strip()
        if not search_query:
            await message.channel.send("Please enter a song name or link after `!play`.")
            return
        
        await message.channel.send(f"🔍 Request received, processing...")
        await handle_play_command(message, search_query)

    # --- !stop ---
    elif message.content.startswith('!stop'):
        if message.guild.voice_client:
            song_queue.clear()
            loop_mode = 0
            message.guild.voice_client.stop()
            await message.guild.voice_client.disconnect()
            await message.channel.send("🛑 Playback stopped, queue cleared, and disconnected.")
        else:
            await message.channel.send("The bot is not currently connected to a voice channel.")

    # --- !skip ---
    elif message.content.startswith('!skip'):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            message.guild.voice_client.stop() 
            await message.channel.send("⏭️ Skipped current song!")
        else:
            await message.channel.send("No music is currently playing.")

    # --- !queue ---
    elif message.content.startswith('!queue'):
        if not song_queue:
            status = "📭 The queue is currently empty."
        else:
            status = "📋 **Queue:**\n"
            for i, (m, u, title) in enumerate(song_queue[:10]):
                status += f"**{i+1}.** {title}\n"
            if len(song_queue) > 10:
                status += f"... and {len(song_queue)-10} more"
        
        # Display Loop Status
        modes = ["❌ Off", "🔁 List Loop"]
        status += f"\n**Loop Mode:** {modes[loop_mode]}"
        
        await message.channel.send(status)

    # --- !loop ---
    elif message.content.startswith('!loop'):
        loop_mode = (loop_mode + 1) % 2 
        modes = ["❌ Loop disabled", "🔁 List loop enabled"]
        await message.channel.send(f"{modes[loop_mode]}")

    # --- !shuffle ---
    elif message.content.startswith('!shuffle'):
        if len(song_queue) < 2:
            await message.channel.send("Not enough songs in the queue to shuffle.")
        else:
            random.shuffle(song_queue)
            await message.channel.send("🔀 Queue shuffled!")

    # --- !remove ---
    elif message.content.startswith('!remove'):
        try:
            index = int(message.content[len('!remove'):].strip()) - 1
            if 0 <= index < len(song_queue):
                removed_song = song_queue.pop(index)
                await message.channel.send(f"🗑️ Removed from queue: **{removed_song[2]}**")
            else:
                await message.channel.send("Song not found. Check the number in `!queue` (Cannot remove currently playing song, use `!skip`).")
        except:
            await message.channel.send("Invalid format. Usage: `!remove 1`")

    # --- !pause / !resume ---
    elif message.content.startswith('!pause'):
        if message.guild.voice_client and message.guild.voice_client.is_playing():
            message.guild.voice_client.pause()
            await message.channel.send("⏸️ Music paused.")
            
    elif message.content.startswith('!resume'):
        if message.guild.voice_client and message.guild.voice_client.is_paused():
            message.guild.voice_client.resume()
            await message.channel.send("▶️ Music resumed.")

# 6. Handle Search and URL Logic
async def handle_play_command(message, query):
    YOUTUBE_URL_REGEX = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=|embed\/|v\/)?([a-zA-Z0-9_-]+)"
    
    if not message.author.voice or not message.author.voice.channel:
        await message.channel.send("You must join a voice channel first!")
        return

    is_url = re.match(YOUTUBE_URL_REGEX, query)
    
    # Case 1: Input is a URL
    if is_url:
        video_id = is_url.group(1)
        final_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Quick extract to get the title
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL({'quiet':True, 'extract_flat':True}).extract_info(final_url, download=False))
            video_title = data.get('title', 'Unknown Song')
        except:
            video_title = "Unknown YouTube Song"

        await message.channel.send(f"🔗 Link identified: **{video_title}**")
        return await play_song(message, final_url, title=video_title)
        
    # Case 2: Input is a Search Term
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
                return await message.channel.send("No results found.")

            search_list = []
            for i, video in enumerate(results[:5]):
                title = video.get('title', 'Unknown Title')
                search_list.append(f"**{i+1}.** {title}")

            await message.channel.send("Please reply with a number (1-5). Cancels automatically in 30s:\n\n" + "\n".join(search_list))

        except Exception as e:
            return await message.channel.send(f"Search error: {e}")
        
        def check(m):
            return (m.author == message.author and 
                    m.channel == message.channel and 
                    m.content.isdigit() and 
                    1 <= int(m.content) <= len(results))

        try:
            selection_message = await bot.wait_for('message', check=check, timeout=30.0)
            selected_index = int(selection_message.content) - 1
            selected_video = results[selected_index]
            
            # Use 'url' directly, never fallback to webpage_url to avoid 403 errors
            final_url = selected_video.get('url')
            # If no direct url is found (rare in search), we can't play it reliably

            video_title = selected_video.get('title', 'Unknown Song')
            await message.channel.send(f"✅ Selected **{video_title}**")
            await play_song(message, final_url, title=video_title)

        except asyncio.TimeoutError:
            await message.channel.send("Selection timed out.")
        except Exception as e:
            await message.channel.send(f"Selection error: {e}")

# 7. Core Play Function
async def play_song(message, url, title="Unknown Song"):
    global song_queue, current_song_info
    
    voice_client = message.guild.voice_client
    if not voice_client:
        try:
            voice_client = await message.author.voice.channel.connect()
        except Exception as e:
            return await message.channel.send(f"Failed to connect to voice: {e}")
            
    # If already playing, add to queue
    if voice_client.is_playing():
        song_queue.append((message, url, title))
        await message.channel.send(f"📝 **{title}** added to queue (Position: {len(song_queue)})")
        return

    # Update current info
    current_song_info = (message, url, title)

    # Extract Stream URL
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
        
        # 1. Try 'url'
        stream_url = data.get('url')
        
        # 2. Try 'formats' if 'url' is missing
        if not stream_url and data.get('formats'):
            for f in data['formats']:
                if f.get('url') and f.get('acodec') != 'none':
                    stream_url = f['url']
                    break
        
        # Note: We removed webpage_url fallback to prevent errors
        
        if not stream_url: raise Exception("Could not extract a valid audio stream")

    except Exception as e:
        print(f"Extraction failed: {e}")
        return await message.channel.send(f"Playback preparation failed: {e}")

    # Start Playback
    try:
        FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        
        audio_source = discord.FFmpegOpusAudio(stream_url, **FFMPEG_OPTIONS, executable=FFMPEG_EXECUTABLE_PATH)
        
        def after_playing(error):
            if error: print(f"Playback error: {error}")
            
            # --- Loop Logic ---
            if loop_mode == 1:
                song_queue.append(current_song_info)
            
            # --- Next Song Logic ---
            if len(song_queue) > 0:
                next_msg, next_url, next_title = song_queue.pop(0)
                coro = play_song(next_msg, next_url, next_title)
                future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            else:
                # --- Auto Disconnect ---
                coro = auto_disconnect(voice_client)
                asyncio.run_coroutine_threadsafe(coro, bot.loop)

        voice_client.play(audio_source, after=after_playing)
        await message.channel.send(f"🎶 Now Playing: **{title}**")

    except Exception as e:
        await message.channel.send(f"Playback error: {e}")

# Auto Disconnect (Wait 2 minutes)
async def auto_disconnect(voice_client):
    await asyncio.sleep(120) 
    if voice_client.is_connected() and not voice_client.is_playing() and len(song_queue) == 0:
        await voice_client.disconnect()
        print("🤖 Idle timeout (2 mins). Disconnected automatically.")

# 8. Run Bot
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
else:
    print("Error: DISCORD_TOKEN not found in .env")
