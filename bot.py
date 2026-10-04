import os
import random
import secrets
import asyncio
import discord
import aiohttp
from discord import app_commands
from discord.ext import commands, tasks

# ==========================================
# 1. DISCORD BOT CONFIGURATION
# ==========================================
intents = discord.Intents.default()
intents.guild_messages = True
intents.message_content = True  # Required for $ prefix commands
intents.members = True          # Required for fetching server members

bot = commands.Bot(command_prefix="$", intents=intents)

# State management
bot_state = {
    "running": False,
    "channel_id": None,
    "webhook_url": None,
    "min_delay": 30,  # Default minimum delay in seconds
    "max_delay": 90,  # Default maximum delay in seconds
    "emojis": {
        "BTC": "🪙",
        "ETH": "🔹",
        "LTC": "⚡"
    }
}

# Crypto configuration settings & colors
CRYPTO_CONFIG = {
    "ETH": {
        "color": 0x4562E6,
        "min_crypto": 0.001,
        "max_crypto": 0.05,
        "usd_rate": 3400.0,
        "tx_prefix": "0x"
    },
    "LTC": {
        "color": 0x838383,
        "min_crypto": 0.1,
        "max_crypto": 2.5,
        "usd_rate": 82.0,
        "tx_prefix": ""
    },
    "BTC": {
        "color": 0xF7931A,
        "min_crypto": 0.0001,
        "max_crypto": 0.005,
        "usd_rate": 62000.0,
        "tx_prefix": ""
    }
}

# ==========================================
# 2. HELPER FUNCTIONS & EMBED GENERATOR
# ==========================================
def generate_random_tx():
    part1 = secrets.token_hex(4)
    part2 = secrets.token_hex(4)
    return f"{part1}...{part2}"

def build_trade_embed(guild: discord.Guild, crypto_type: str) -> discord.Embed:
    cfg = CRYPTO_CONFIG[crypto_type]
    
    amount = round(random.uniform(cfg["min_crypto"], cfg["max_crypto"]), 6)
    usd_val = round(amount * cfg["usd_rate"], 2)
    tx_id = f"{cfg['tx_prefix']}{generate_random_tx()}"
    
    non_bot_members = [m for m in guild.members if not m.bot]
    selected_member = random.choice(non_bot_members) if non_bot_members else guild.me
    
    emoji = bot_state["emojis"].get(crypto_type, "")

    embed = discord.Embed(
        title=f"{emoji} Trade Completed".strip(),
        color=cfg["color"]
    )
    
    embed.add_field(
        name="",
        value=f"`{amount:.6f}` **{crypto_type}** (`${usd_val:,.2f} USD`)",
        inline=False
    )
    
    embed.add_field(
        name="───────────────",
        value="",
        inline=False
    )
    
    embed.add_field(
        name="Sender",
        value="`[Anonymous]`",
        inline=False
    )
    
    embed.add_field(
        name="Receiver",
        value=f"{selected_member.mention}",
        inline=False
    )
    
    embed.add_field(
        name="Transaction ID",
        value=f"`{tx_id}`",
        inline=False
    )
    
    return embed

# Loop task to send trade embeds with random configurable delays
async def embed_sender_loop():
    while bot_state["running"]:
        # Pick random delay between min_delay and max_delay
        delay = random.randint(bot_state["min_delay"], bot_state["max_delay"])
        await asyncio.sleep(delay)

        if not bot_state["running"] or not bot_state["channel_id"]:
            break

        channel = bot.get_channel(bot_state["channel_id"])
        if not channel:
            continue

        crypto_choice = random.choice(["BTC", "ETH", "LTC"])
        embed = build_trade_embed(channel.guild, crypto_choice)
        
        try:
            if bot_state["webhook_url"]:
                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.from_url(bot_state["webhook_url"], session=session)
                    await webhook.send(embed=embed, username="Trade Bot")
            else:
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Error sending embed: {e}")

# Global reference to hold background sending task
sender_task = None

# ==========================================
# 3. BOT COMMANDS ($ PREFIX & SLASH)
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot is logged in and online as {bot.user}")

# $sync command (Message Prefix)
@bot.command(name="sync")
async def prefix_sync(ctx: commands.Context, scope: str = "guild"):
    try:
        if scope.lower() == "guild":
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"🔄 Guild sync complete! Registered **{len(synced)}** command(s) to this server.")
        elif scope.lower() == "global":
            synced = await bot.tree.sync()
            await ctx.send(f"🌐 Global sync complete! Registered **{len(synced)}** command(s) globally.")
        else:
            await ctx.send("Usage: `$sync` or `$sync global`")
    except Exception as e:
        await ctx.send(f"❌ Failed to sync: {e}")

# /sync command (Slash Command)
@bot.tree.command(name="sync", description="Syncs slash commands and cleans up old ones")
@app_commands.describe(scope="Sync scope: 'guild' (instant) or 'global'")
async def slash_sync(interaction: discord.Interaction, scope: str = "guild"):
    await interaction.response.defer(ephemeral=True)
    
    try:
        if scope.lower() == "guild":
            bot.tree.copy_global_to(guild=interaction.guild)
            synced = await bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(
                f"🔄 Guild sync complete! Registered **{len(synced)}** command(s).",
                ephemeral=True
            )
        elif scope.lower() == "global":
            synced = await bot.tree.sync()
            await interaction.followup.send(
                f"🌐 Global sync complete! Registered **{len(synced)}** command(s) globally.",
                ephemeral=True
            )
        else:
            await interaction.followup.send("Please specify either `guild` or `global`.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to sync commands: {e}", ephemeral=True)

@bot.tree.command(name="start", description="Start sending trade completion embeds")
@app_commands.describe(
    webhook_url="Optional Discord Webhook URL to send through",
    min_delay_seconds="Minimum delay between embeds (default: 30s)",
    max_delay_seconds="Maximum delay between embeds (default: 90s)",
    btc_emoji="Custom emoji for BTC",
    eth_emoji="Custom emoji for ETH",
    ltc_emoji="Custom emoji for LTC"
)
async def start_cmd(
    interaction: discord.Interaction,
    webhook_url: str = None,
    min_delay_seconds: int = 30,
    max_delay_seconds: int = 90,
    btc_emoji: str = None,
    eth_emoji: str = None,
    ltc_emoji: str = None
):
    global sender_task

    if btc_emoji:
        bot_state["emojis"]["BTC"] = btc_emoji
    if eth_emoji:
        bot_state["emojis"]["ETH"] = eth_emoji
    if ltc_emoji:
        bot_state["emojis"]["LTC"] = ltc_emoji

    bot_state["min_delay"] = max(5, min_delay_seconds)
    bot_state["max_delay"] = max(bot_state["min_delay"], max_delay_seconds)
    bot_state["running"] = True
    bot_state["channel_id"] = interaction.channel_id
    bot_state["webhook_url"] = webhook_url

    # Cancel previous running loop if any
    if sender_task and not sender_task.done():
        sender_task.cancel()

    # Start new sender loop task
    sender_task = asyncio.create_task(embed_sender_loop())

    await interaction.response.send_message(
        f"✅ Trade generator started!\n⏱️ Embeds will send randomly every **{bot_state['min_delay']}s** to **{bot_state['max_delay']}s**.",
        ephemeral=True
    )

@bot.tree.command(name="stop", description="Stop the embed generator")
async def stop_cmd(interaction: discord.Interaction):
    global sender_task
    bot_state["running"] = False
    
    if sender_task and not sender_task.done():
        sender_task.cancel()

    await interaction.response.send_message(
        "🛑 Trade embed generator stopped.",
        ephemeral=True
    )

# ==========================================
# 4. BOT EXECUTION
# ==========================================
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_TOKEN environment variable is not set.")
