import os
import random
import secrets
import threading
import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask

# ==========================================
# 1. FLASK WEB SERVER (For Railway Health Check)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running online!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Start Flask on a separate background thread
threading.Thread(target=run_flask, daemon=True).start()

# ==========================================
# 2. DISCORD BOT CONFIGURATION
# ==========================================
intents = discord.Intents.default()
intents.guild_messages = True
intents.members = True  # Required to select random server members

bot = commands.Bot(command_prefix="!", intents=intents)

# State management
bot_state = {
    "running": False,
    "channel_id": None,
    "webhook_url": None,
    "emojis": {
        "BTC": "🪙",
        "ETH": "🔹",
        "LTC": "⚡"
    }
}

# Crypto configuration settings & colors
CRYPTO_CONFIG = {
    "ETH": {
        "color": 0x4562E6,  # Blue/Purple hue
        "min_crypto": 0.001,
        "max_crypto": 0.05,
        "usd_rate": 3400.0,
        "tx_prefix": "0x"
    },
    "LTC": {
        "color": 0x838383,  # Silver/Grey hue
        "min_crypto": 0.1,
        "max_crypto": 2.5,
        "usd_rate": 82.0,
        "tx_prefix": ""
    },
    "BTC": {
        "color": 0xF7931A,  # Orange hue
        "min_crypto": 0.0001,
        "max_crypto": 0.005,
        "usd_rate": 62000.0,
        "tx_prefix": ""
    }
}

# ==========================================
# 3. HELPER FUNCTIONS & EMBED GENERATOR
# ==========================================
def generate_random_tx():
    part1 = secrets.token_hex(4)
    part2 = secrets.token_hex(4)
    return f"{part1}...{part2}"

def build_trade_embed(guild: discord.Guild, crypto_type: str) -> discord.Embed:
    cfg = CRYPTO_CONFIG[crypto_type]
    
    # Generate random transaction amounts
    amount = round(random.uniform(cfg["min_crypto"], cfg["max_crypto"]), 6)
    usd_val = round(amount * cfg["usd_rate"], 2)
    tx_id = f"{cfg['tx_prefix']}{generate_random_tx()}"
    
    # Fetch random member from guild
    non_bot_members = [m for m in guild.members if not m.bot]
    selected_member = random.choice(non_bot_members) if non_bot_members else guild.me
    
    # Retrieve configured emoji
    emoji = bot_state["emojis"].get(crypto_type, "")

    embed = discord.Embed(
        title=f"{emoji} Trade Completed".strip(),
        color=cfg["color"]
    )
    
    # Amount Field
    embed.add_field(
        name="",
        value=f"`{amount:.6f}` **{crypto_type}** (`${usd_val:,.2f} USD`)",
        inline=False
    )
    
    # Divider separator line simulated via field
    embed.add_field(
        name="───────────────",
        value="",
        inline=False
    )
    
    # Sender
    embed.add_field(
        name="Sender",
        value="`[Anonymous]`",
        inline=False
    )
    
    # Receiver
    embed.add_field(
        name="Receiver",
        value=f"{selected_member.mention}",
        inline=False
    )
    
    # Transaction ID
    embed.add_field(
        name="Transaction ID",
        value=f"`{tx_id}`",
        inline=False
    )
    
    return embed

# Loop to send randomized embeds every 30 to 120 seconds
@tasks.loop(seconds=45)
async def embed_sender_task():
    if not bot_state["running"] or not bot_state["channel_id"]:
        return

    channel = bot.get_channel(bot_state["channel_id"])
    if not channel:
        return

    # Pick 1 of 3 types randomly
    crypto_choice = random.choice(["BTC", "ETH", "LTC"])
    embed = build_trade_embed(channel.guild, crypto_choice)
    
    try:
        # Check if webhook URL is set; send via Webhook if available
        if bot_state["webhook_url"]:
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(bot_state["webhook_url"], session=session)
                await webhook.send(embed=embed, username="Trade Bot")
        else:
            await channel.send(embed=embed)
    except Exception as e:
        print(f"Error sending embed: {e}")

# ==========================================
# 4. BOT SLASH COMMANDS
# ==========================================
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="start", description="Start sending trade completion embeds")
@app_commands.describe(
    webhook_url="Optional Discord Webhook URL to send through",
    btc_emoji="Custom emoji for BTC (e.g. :btc:)",
    eth_emoji="Custom emoji for ETH (e.g. :eth:)",
    ltc_emoji="Custom emoji for LTC (e.g. :ltc:)"
)
async def start_cmd(
    interaction: discord.Interaction,
    webhook_url: str = None,
    btc_emoji: str = None,
    eth_emoji: str = None,
    ltc_emoji: str = None
):
    if btc_emoji:
        bot_state["emojis"]["BTC"] = btc_emoji
    if eth_emoji:
        bot_state["emojis"]["ETH"] = eth_emoji
    if ltc_emoji:
        bot_state["emojis"]["LTC"] = ltc_emoji

    bot_state["running"] = True
    bot_state["channel_id"] = interaction.channel_id
    bot_state["webhook_url"] = webhook_url

    if not embed_sender_task.is_running():
        embed_sender_task.start()

    await interaction.response.send_message(
        "✅ Trade embed generator started! Webhook and custom server emojis updated.",
        ephemeral=True
    )

@bot.tree.command(name="stop", description="Stop the embed generator")
async def stop_cmd(interaction: discord.Interaction):
    bot_state["running"] = False
    if embed_sender_task.is_running():
        embed_sender_task.stop()

    await interaction.response.send_message(
        "🛑 Trade embed generator has been stopped.",
        ephemeral=True
    )

# ==========================================
# 5. BOT EXECUTION
# ==========================================
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_TOKEN environment variable not set.")
