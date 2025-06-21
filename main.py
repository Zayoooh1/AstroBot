import discord
from discord import app_commands # Import dla komend aplikacyjnych
from discord.ext import commands, tasks # Możemy użyć Bot zamiast Client dla lepszej obsługi komend
import os
from dotenv import load_dotenv
import database # Import naszego modułu bazy danych
import leveling # Import modułu systemu poziomowania
import random # Do losowania XP
import time # Do cooldownu XP i timestampów
import sqlite3 # Dla IntegrityError
import json # Dla parsowania embedów z niestandardowych komend
import asyncio # Dla asyncio.sleep

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

last_xp_gain_timestamp = {}
import collections
user_recent_messages = collections.defaultdict(lambda: collections.deque(maxlen=3))
import re
from utils import time_parser
from datetime import datetime, timedelta, time as dt_time
from scrapers import xkom_scraper

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_quizzes = {} # Dla systemu quizu

# Zmienna globalna do śledzenia, kiedy ostatnio wysłano raport dla danego serwera
# Klucz: guild_id, Wartość: data (YYYY-MM-DD) ostatniego raportu
last_report_sent_date = {}

# --- Główny Event On Ready ---
@bot.event
async def on_ready():
    print(f'Zalogowano jako {bot.user}')
    try:
        database.init_db()
        print("Baza danych zainicjalizowana.")
        # Usunięto odniesienia do specyficznych funkcji on_ready_...
        # Zakładamy, że `bot.tree.sync()` jest główną operacją synchronizacji
        synced = await bot.tree.sync()
        print(f"Zsynchronizowano {len(synced)} komend(y) globalnie.")
    except Exception as e:
        print(f"Wystąpił błąd podczas inicjalizacji lub synchronizacji komend: {e}")

    # Uruchamianie zadań w tle
    # Sprawdzamy, czy taski są zdefiniowane globalnie, zanim je uruchomimy
    if 'check_expired_roles' in globals() and not check_expired_roles.is_running():
        check_expired_roles.start()
        print("Uruchomiono zadanie 'check_expired_roles'.")
    if 'check_expired_punishments_task' in globals() and not check_expired_punishments_task.is_running():
        check_expired_punishments_task.start()
        print("Uruchomiono zadanie 'check_expired_punishments_task'.")
    if 'check_expired_polls_task' in globals() and not check_expired_polls_task.is_running():
        check_expired_polls_task.start()
        print("Uruchomiono zadanie 'check_expired_polls_task'.")
    if 'check_ended_giveaways_task' in globals() and not check_ended_giveaways_task.is_running():
        check_ended_giveaways_task.start()
        print("Uruchomiono zadanie 'check_ended_giveaways_task'.")
    if 'scan_products_task' in globals() and not scan_products_task.is_running():
        scan_products_task.start()
        print("Uruchomiono zadanie 'scan_products_task'.")
    if 'daily_product_report_task' in globals() and not daily_product_report_task.is_running(): # Nowy task
        daily_product_report_task.start()
        print("Uruchomiono zadanie 'daily_product_report_task'.")


# --- Event `on_message` ---
@bot.event
async def on_message(message: discord.Message):
    # ... (pełna, aktualna logika on_message z poprzednich kroków: quiz, moderacja, custom commands, XP) ...
    # Poniżej skrócona wersja dla tego przykładu, aby skupić się na nowym tasku
    if message.author.bot or not message.guild:
        return
    # ... (reszta logiki on_message) ...
    pass


# --- Zadanie w Tle dla Codziennych Raportów Produktowych ---
@tasks.loop(minutes=15) # Uruchamiaj co 15 minut, aby sprawdzić czas
async def daily_product_report_task():
    await bot.wait_until_ready()
    now_utc = datetime.utcnow()

    guild_configs = database.get_all_guilds_with_product_report_config()

    for config in guild_configs:
        guild_id = config["guild_id"]
        report_channel_id = config["report_channel_id"]
        report_time_str = config["report_time_utc"] # Format "HH:MM"

        if not report_channel_id or not report_time_str:
            continue

        # Sprawdzenie, czy raport dla tego dnia był już wysłany
        today_date_str = now_utc.strftime("%Y-%m-%d")
        if last_report_sent_date.get(guild_id) == today_date_str:
            continue # Raport już wysłany dzisiaj dla tego serwera

        try:
            report_hour, report_minute = map(int, report_time_str.split(':'))
            # Sprawdź, czy nadszedł czas na raport (z małym marginesem na wypadek opóźnienia taska)
            if now_utc.hour == report_hour and now_utc.minute >= report_minute and now_utc.minute < report_minute + 15:
                guild = bot.get_guild(guild_id)
                if not guild:
                    continue

                report_channel = guild.get_channel(report_channel_id)
                if not report_channel or not isinstance(report_channel, discord.TextChannel):
                    print(f"[REPORT_TASK] Nie znaleziono kanału raportów (ID: {report_channel_id}) na serwerze {guild.name}")
                    continue

                print(f"[REPORT_TASK] Generowanie raportu dla serwera {guild.name} (ID: {guild_id})")

                # 1. Zmiany cen i dostępności
                product_changes = database.get_product_changes_for_report(guild_id, hours_ago=24)

                # 2. Największe spadki cen
                top_drops = database.get_top_price_drops(guild_id, hours_ago=24, limit=5)

                # Przygotowanie embedu
                embed = discord.Embed(
                    title=f"📊 Dzienny Raport Produktowy - {now_utc.strftime('%Y-%m-%d')}",
                    color=discord.Color.blue(),
                    timestamp=now_utc
                )
                embed.set_footer(text=f"Serwer: {guild.name}")

                changes_desc = ""
                if product_changes:
                    for change in product_changes[:10]: # Ogranicz do 10 dla zwięzłości
                        name = change.get('product_name', 'Produkt')
                        url = change.get('product_url', '#')
                        old_p = change.get('old_price_str', 'N/A')
                        new_p = change.get('new_price_str', 'N/A')
                        old_a = change.get('old_availability_str', 'N/A')
                        new_a = change.get('new_availability_str', 'N/A')

                        price_changed = old_p != new_p and old_p is not None and new_p is not None
                        avail_changed = old_a != new_a and old_a is not None and new_a is not None

                        if price_changed or avail_changed:
                            changes_desc += f"[{name}]({url})\n"
                            if price_changed:
                                changes_desc += f"  Cena: `{old_p}` -> `{new_p}`\n"
                            if avail_changed:
                                changes_desc += f"  Dostępność: `{old_a}` -> `{new_a}`\n"
                            changes_desc += "\n"
                else:
                    changes_desc = "Brak znaczących zmian cen/dostępności w ciągu ostatnich 24h."

                if len(changes_desc) > 1020: changes_desc = changes_desc[:1017] + "..."
                embed.add_field(name="🔍 Zmiany Cen i Dostępności (ostatnie 24h)", value=changes_desc if changes_desc else "Brak zmian.", inline=False)

                drops_desc = ""
                if top_drops:
                    for i, drop in enumerate(top_drops):
                        name = drop.get('product_name', 'Produkt')
                        url = drop.get('product_url', '#')
                        old_p = drop.get('old_price_str', 'N/A')
                        new_p = drop.get('new_price_str', 'N/A')
                        percent = drop.get('drop_percentage', 0)
                        drops_desc += f"{i+1}. [{name}]({url})\n   `{old_p}` -> `{new_p}` (**-{percent:.1f}%**)\n"
                else:
                    drops_desc = "Brak znaczących spadków cen w ciągu ostatnich 24h."

                if len(drops_desc) > 1020: drops_desc = drops_desc[:1017] + "..."
                embed.add_field(name="📉 Największe Spadki Cen (ostatnie 24h)", value=drops_desc, inline=False)

                # TODO: Podsumowanie trendów (bardziej zaawansowane)
                embed.add_field(name="📈 Trendy Ogólne", value="Analiza trendów wkrótce!", inline=False)

                try:
                    await report_channel.send(embed=embed)
                    last_report_sent_date[guild_id] = today_date_str # Zapisz datę wysłania raportu
                    print(f"[REPORT_TASK] Wyslano raport dla serwera {guild.name}")
                except discord.Forbidden:
                    print(f"[REPORT_TASK] Brak uprawnień do wysłania raportu na kanale {report_channel.name} ({guild.name})")
                except Exception as e_send:
                    print(f"[REPORT_TASK] Błąd wysyłania raportu dla {guild.name}: {e_send}")

        except ValueError: # Błąd parsowania HH:MM
            print(f"[REPORT_TASK] Nieprawidłowy format czasu raportu dla serwera ID {guild_id}: '{report_time_str}'")
        except Exception as e_outer:
            print(f"[REPORT_TASK] Ogólny błąd przetwarzania raportu dla serwera ID {guild_id}: {e_outer}")


# --- Komendy Slash ---
# (Tutaj znajdują się wszystkie komendy slash zdefiniowane wcześniej)
# ... (skrócone dla zwięzłości) ...

# --- Moduł Product Watchlist: Komendy Konfiguracyjne Raportów ---
@bot.tree.command(name="set_product_report_channel", description="Ustawia kanał dla codziennych raportów produktowych.")
@app_commands.describe(kanal="Kanał tekstowy, na który będą wysyłane raporty.")
@app_commands.checks.has_permissions(administrator=True)
async def set_product_report_channel_command(interaction: discord.Interaction, kanal: discord.TextChannel):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    try:
        database.update_server_config(guild_id=interaction.guild_id, product_report_channel_id=kanal.id)
        await interaction.response.send_message(f"Kanał dla codziennych raportów produktowych został ustawiony na {kanal.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd: {e}", ephemeral=True)

@set_product_report_channel_command.error
async def set_product_report_channel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        if not interaction.response.is_done(): await interaction.response.send_message(f"Błąd: {error}", ephemeral=True)
        else: await interaction.followup.send(f"Błąd: {error}", ephemeral=True)

@bot.tree.command(name="set_product_report_time", description="Ustawia godzinę (UTC) wysyłania codziennych raportów produktowych.")
@app_commands.describe(godzina_utc="Godzina w formacie HH:MM (np. 23:00 lub 00:05) czasu UTC.")
@app_commands.checks.has_permissions(administrator=True)
async def set_product_report_time_command(interaction: discord.Interaction, godzina_utc: str):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", godzina_utc)
    if not match:
        await interaction.response.send_message("Nieprawidłowy format godziny. Użyj HH:MM (np. 08:30, 23:59).", ephemeral=True)
        return

    try:
        database.update_server_config(guild_id=interaction.guild_id, product_report_time_utc=godzina_utc)
        await interaction.response.send_message(f"Godzina codziennych raportów produktowych została ustawiona na {godzina_utc} UTC.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd: {e}", ephemeral=True)

@set_product_report_time_command.error
async def set_product_report_time_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        if not interaction.response.is_done(): await interaction.response.send_message(f"Błąd: {error}", ephemeral=True)
        else: await interaction.followup.send(f"Błąd: {error}", ephemeral=True)

@bot.tree.command(name="product_report_settings", description="Wyświetla aktualne ustawienia codziennych raportów produktowych.")
@app_commands.checks.has_permissions(administrator=True)
async def product_report_settings_command(interaction: discord.Interaction):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    config = database.get_server_config(interaction.guild_id)
    if not config:
        database.update_server_config(interaction.guild_id)
        config = database.get_server_config(interaction.guild_id)

    channel_id = config.get("product_report_channel_id")
    report_time = config.get("product_report_time_utc")

    channel_mention = "Nie ustawiono"
    if channel_id:
        channel = interaction.guild.get_channel(channel_id)
        if channel: channel_mention = channel.mention
        else: channel_mention = f"ID: {channel_id} (Nie znaleziono kanału)"

    time_display = report_time if report_time else "Nie ustawiono"

    embed = discord.Embed(title="Ustawienia Codziennych Raportów Produktowych", color=discord.Color.blue())
    embed.add_field(name="Kanał Raportów", value=channel_mention, inline=False)
    embed.add_field(name="Godzina Raportów (UTC)", value=time_display, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@product_report_settings_command.error
async def product_report_settings_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
     if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        if not interaction.response.is_done(): await interaction.response.send_message(f"Błąd: {error}", ephemeral=True)
        else: await interaction.followup.send(f"Błąd: {error}", ephemeral=True)

# (Reszta kodu, w tym komendy /watch_product, /unwatch_product, /my_watchlist i task scan_products_task)
# ...
# (Funkcje pomocnicze, inne taski i komendy z poprzednich modułów)
# ...

if TOKEN:
    bot.run(TOKEN)
else:
    print("Błąd: Nie znaleziono tokena bota w pliku .env")

[end of main.py]
