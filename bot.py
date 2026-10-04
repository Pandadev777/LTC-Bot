import os
import random
import secrets
import asyncio
import discord
import aiohttp
from discord import app_commands
from discord.ext import commands

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
    "min_delay": 30,
    "max_delay": 90,
    "min_usd": 15.0,   # Minimum trade value in USD
    "max_usd": 150.0,  # Maximum trade value in USD
    "emojis": {
        "BTC": "🪙",
        "ETH": "🔹",
        "LTC": "⚡"
    }
}

# Base config & colors
CRYPTO_CONFIG = {
    "ETH": {
        "color": 0x4562E6,
        "coingecko_id": "ethereum",
        "fallback_rate": 3000.0,
        "tx_prefix": "0x",
        "decimals": 6
    },
    "LTC": {
        "color": 0x838383,
        "coingecko_id": "litecoin",
        "fallback_rate": 80.0,
        "tx_prefix": "",
        "decimals": 5
    },
    "BTC": {
        "color": 0xF7931A,
        "coingecko_id": "bitcoin",
        "fallback_rate": 65000.0,
        "tx_prefix": "",
        "decimals": 8
    }
}

# ==========================================
# 2. PRICE FETCHING & EMBED GENERATOR
# ==========================================
async def get_live_prices():
    """Fetches real-time crypto USD rates from CoinGecko API."""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,litecoin&vs_currencies=usd"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "BTC": data.get("bitcoin", {}).get("usd", CRYPTO_CONFIG["BTC"]["fallback_rate"]),
                        "ETH": data.get("ethereum", {}).get("usd", CRYPTO_CONFIG["ETH"]["fallback_rate"]),
                        "LTC": data.get("litecoin", {}).get("usd", CRYPTO_CONFIG["LTC"]["fallback_rate"])
                    }
    except Exception as e:
        print(f"Warning: Failed to fetch live prices, using fallbacks. Error: {e}")
    
    # Fallback to configured default rates if API call fails
    return {
        "BTC": CRYPTO_CONFIG["BTC"]["fallback_rate"],
        "ETH": CRYPTO_CONFIG["ETH"]["fallback_rate"],
        "LTC": CRYPTO_CONFIG["LTC"]["fallback_rate"]
    }

def generate_random_tx():
    part1 = secrets.token_hex(4)
    part2 = secrets.token_hex(4)
    return f"{part1}...{part2}"

def build_trade_embed(guild: discord.Guild, crypto_type: str, live_rate: float) -> discord.Embed:
    cfg = CRYPTO_CONFIG[crypto_type]
    
    # Generate random target USD trade value
    target_usd = round(random.uniform(bot_state["min_usd"], bot_state["max_usd"]), 2)
    
    # Calculate exact crypto amount from market conversion rate
    crypto_amount = target_usd / live_rate
    crypto_amount_fmt = f"{crypto_amount:.{cfg['decimals']}f}"
    
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
        value=f"`{crypto_amount_fmt}` **{crypto_type}** (`${target_usd:,.2f} USD`)",
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

# Loop task to send trade embeds using live market conversions
async def embed_sender_loop():
    while bot_state["running"]:
        delay = random.randint(bot_state["min_delay"], bot_state["max_delay"])
        await asyncio.sleep(delay)

        if not bot_state["running"] or not bot_state["channel_id"]:
            break

        channel = bot.get_channel(bot_state["channel_id"])
        if not channel:
            continue

        # Fetch current market rates
        prices = await get_live_prices()
        
        crypto_choice = random.choice(["BTC", "ETH", "LTC"])
        live_rate = prices.get(crypto_choice, CRYPTO_CONFIG[crypto_choice]["fallback_rate"])
        
        embed = build_trade_embed(channel.guild, crypto_choice, live_rate)
        
        try:
            if bot_state["webhook_url"]:
                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.from_url(bot_state["webhook_url"], session=session)
                    await webhook.send(embed=embed, username="Trade Bot")
            else:
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Error sending embed: {e}")

sender_task = None

# ==========================================
# 3. BOT COMMANDS ($ PREFIX & SLASH)
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot is logged in and online as {bot.user}")

# $sync command
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

# /sync command
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
    min_delay_seconds="Minimum delay between embeds in seconds (default: 30)",
    max_delay_seconds="Maximum delay between embeds in seconds (default: 90)",
    min_usd="Minimum USD value for trade (default: 15.0)",
    max_usd="Maximum USD value for trade (default: 150.0)",
    btc_emoji="Custom emoji for BTC",
    eth_emoji="Custom emoji for ETH",
    ltc_emoji="Custom emoji for LTC"
)
async def start_cmd(
    interaction: discord.Interaction,
    webhook_url: str = None,
    min_delay_seconds: int = 30,
    max_delay_seconds: int = 90,
    min_usd: float = 15.0,
    max_usd: float = 150.0,
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
    bot_state["min_usd"] = min_usd
    bot_state["max_usd"] = max_usd
    bot_state["running"] = True
    bot_state["channel_id"] = interaction.channel_id
    bot_state["webhook_url"] = webhook_url

    if sender_task and not sender_task.done():
        sender_task.cancel()

    sender_task = asyncio.create_task(embed_sender_loop())

    await interaction.response.send_message(
        f"✅ Trade generator started!\n"
        f"⏱️ Delay: **{bot_state['min_delay']}s** to **{bot_state['max_delay']}s**\n"
        f"💵 Value range: **${bot_state['min_usd']:.2f}** to **${bot_state['max_usd']:.2f} USD** (Calculated live)",
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
