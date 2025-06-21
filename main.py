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
active_quizzes = {}
last_report_sent_date = {}

# --- Funkcje Pomocnicze (jeśli nie ma ich w osobnych plikach) ---
# Zakładam, że funkcje takie jak send_quiz_question_dm, process_quiz_results,
# log_moderation_action, _handle_giveaway_end_logic są zdefiniowane gdzieś w tym pliku
# (zostały pominięte w ostatnich read_files dla zwięzłości)
# Jeśli ich brakuje, trzeba by je tu wkleić.
async def send_quiz_question_dm(user: discord.User): # Placeholder
    pass
async def process_quiz_results(user: discord.User): # Placeholder
    pass
async def log_moderation_action(*args, **kwargs): # Placeholder
    pass
async def _handle_giveaway_end_logic(*args, **kwargs): # Placeholder
    pass

# --- Główny Event On Ready ---
@bot.event
async def on_ready():
    print(f'Zalogowano jako {bot.user}')
    try:
        database.init_db()
        print("Baza danych zainicjalizowana.")
        synced = await bot.tree.sync()
        print(f"Zsynchronizowano {len(synced)} komend(y) globalnie.")
    except Exception as e:
        print(f"Wystąpił błąd podczas inicjalizacji lub synchronizacji komend: {e}")

    # Uruchamianie zadań w tle
    task_map = {
        "check_expired_roles": check_expired_roles,
        "check_expired_punishments_task": check_expired_punishments_task,
        "check_expired_polls_task": check_expired_polls_task,
        "check_ended_giveaways_task": check_ended_giveaways_task,
        "scan_products_task": scan_products_task,
        "daily_product_report_task": daily_product_report_task
    }
    for task_name_str, task_obj in task_map.items():
        if task_obj and hasattr(task_obj, 'start') and not task_obj.is_running():
            try:
                task_obj.start()
                print(f"Uruchomiono zadanie '{task_name_str}'.")
            except RuntimeError as e:
                 print(f"Błąd podczas uruchamiania zadania '{task_name_str}': {e} (Możliwe, że już działa lub problem z pętlą zdarzeń)")


# --- Event `on_message` ---
@bot.event
async def on_message(message: discord.Message):
    if isinstance(message.channel, discord.DMChannel) and message.author.id in active_quizzes and not message.author.bot:
        user_id_quiz = message.author.id
        quiz_state = active_quizzes[user_id_quiz]
        if quiz_state["current_q_index"] < len(quiz_state["questions"]):
            quiz_state["answers"].append(message.content)
            quiz_state["current_q_index"] += 1
            await send_quiz_question_dm(message.author)
        return

    if message.author.bot or not message.guild:
        return

    message_deleted_by_moderation = False
    server_config = database.get_server_config(message.guild.id)

    if server_config:
        # Logika Moderacji
        if server_config.get("filter_profanity_enabled", True):
            banned_words_list = database.get_banned_words(message.guild.id)
            if banned_words_list:
                for banned_word in banned_words_list:
                    pattern = r"(?i)\b" + re.escape(banned_word) + r"\b"
                    if re.search(pattern, message.content):
                        try:
                            await message.delete()
                            # await log_moderation_action(message.guild, message.author, message.content, f"Wykryto zakazane słowo: '{banned_word}'", message.channel, server_config.get("moderation_log_channel_id"))
                            message_deleted_by_moderation = True
                            try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (niedozwolone słownictwo).")
                            except: pass
                        except Exception as e: print(f"Błąd auto-moderacji (profanity): {e}")
                        break
        if not message_deleted_by_moderation and server_config.get("filter_invites_enabled", True):
            invite_pattern = r"(discord\.(gg|me|io|com\/invite)\/[a-zA-Z0-9]+)"
            if re.search(invite_pattern, message.content, re.IGNORECASE):
                try:
                    await message.delete()
                    # await log_moderation_action(message.guild, message.author, message.content, "Wykryto link zapraszający Discord.", message.channel, server_config.get("moderation_log_channel_id"))
                    message_deleted_by_moderation = True
                    try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (linki zapraszające).")
                    except: pass
                except Exception as e: print(f"Błąd auto-moderacji (invites): {e}")
        if not message_deleted_by_moderation and server_config.get("filter_spam_enabled", True):
            user_msgs = user_recent_messages[message.author.id]
            user_msgs.append(message.content)
            if len(user_msgs) == user_msgs.maxlen and len(set(user_msgs)) == 1:
                try:
                    await message.delete()
                    # await log_moderation_action(message.guild, message.author, message.content, "Wykryto powtarzające się wiadomości (spam).", message.channel, server_config.get("moderation_log_channel_id"))
                    message_deleted_by_moderation = True
                    try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (spam).")
                    except: pass
                except Exception as e: print(f"Błąd auto-moderacji (spam-repeat): {e}")
            if not message_deleted_by_moderation and (len(message.mentions) + len(message.role_mentions) > 5) :
                try:
                    await message.delete()
                    # await log_moderation_action(message.guild, message.author, message.content, "Wykryto nadmierną liczbę wzmianek (spam).", message.channel, server_config.get("moderation_log_channel_id"))
                    message_deleted_by_moderation = True
                    try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (nadmierne wzmianki).")
                    except: pass
                except Exception as e: print(f"Błąd auto-moderacji (spam-mentions): {e}")

    if message_deleted_by_moderation:
        return

    if server_config:
        prefix = server_config.get("custom_command_prefix", "!")
        if message.content.startswith(prefix):
            command_full = message.content[len(prefix):]
            command_name = command_full.split(" ")[0].lower()
            if command_name:
                custom_command_data = database.get_custom_command(message.guild.id, command_name)
                if custom_command_data:
                    response_type = custom_command_data["response_type"]
                    response_content = custom_command_data["response_content"]
                    try:
                        if response_type == "text":
                            await message.channel.send(response_content)
                        elif response_type == "embed":
                            embed_data = json.loads(response_content)
                            if 'timestamp' in embed_data: del embed_data['timestamp']
                            embed_to_send = discord.Embed.from_dict(embed_data)
                            await message.channel.send(embed=embed_to_send)
                        print(f"Wykonano niestandardową komendę '{prefix}{command_name}' przez {message.author.name}")
                        return
                    except json.JSONDecodeError:
                        print(f"Błąd (custom command): Niepoprawny JSON dla '{prefix}{command_name}'")
                    except Exception as e_custom:
                        print(f"Błąd wykonania custom command '{prefix}{command_name}': {e_custom}")

    guild_id = message.guild.id
    user_id = message.author.id
    current_time = time.time()
    user_cooldown_key = (guild_id, user_id)
    last_gain = last_xp_gain_timestamp.get(user_cooldown_key, 0)

    if current_time - last_gain > leveling.XP_COOLDOWN_SECONDS:
        xp_to_add = random.randint(leveling.XP_PER_MESSAGE_MIN, leveling.XP_PER_MESSAGE_MAX)
        new_total_xp = database.add_xp(guild_id, user_id, xp_to_add)
        last_xp_gain_timestamp[user_cooldown_key] = current_time

        user_stats_xp = database.get_user_stats(guild_id, user_id)
        current_level_db_xp = user_stats_xp['level']
        calculated_level_xp = leveling.get_level_from_xp(new_total_xp)

        if calculated_level_xp > current_level_db_xp:
            database.set_user_level(guild_id, user_id, calculated_level_xp)
            try:
                level_up_message_parts = [f"🎉 Gratulacje {message.author.mention}! Osiągnąłeś/aś **Poziom {calculated_level_xp}**!"]
                level_rewards = database.get_rewards_for_level(guild_id, calculated_level_xp)
                awarded_roles_mentions = []

                if level_rewards:
                    member_obj = message.author
                    for reward in level_rewards:
                        if reward.get("role_id_to_grant"):
                            role_to_grant = message.guild.get_role(reward["role_id_to_grant"])
                            if role_to_grant and role_to_grant not in member_obj.roles:
                                if message.guild.me.top_role > role_to_grant and message.guild.me.guild_permissions.manage_roles:
                                    try:
                                        await member_obj.add_roles(role_to_grant, reason=f"Nagroda za osiągnięcie poziomu {calculated_level_xp}")
                                        awarded_roles_mentions.append(role_to_grant.mention)
                                        print(f"Przyznano rolę '{role_to_grant.name}' użytkownikowi {member_obj.name} za poziom {calculated_level_xp}.")
                                    except Exception as e_role:
                                        print(f"Błąd przyznawania roli-nagrody '{role_to_grant.name}' użytkownikowi {member_obj.name}: {e_role}")
                                else:
                                    print(f"Bot nie może przyznać roli-nagrody '{role_to_grant.name}' (problem z hierarchią lub uprawnieniami) użytkownikowi {member_obj.name}.")

                        if reward.get("custom_message_on_level_up"):
                            try:
                                formatted_msg = reward["custom_message_on_level_up"].format(user=member_obj.mention, level=calculated_level_xp, guild_name=message.guild.name)
                                level_up_message_parts.append(formatted_msg)
                            except KeyError as e_format:
                                print(f"Błąd formatowania wiadomości nagrody za poziom: Nieznany placeholder {e_format}. Wiadomość: {reward['custom_message_on_level_up']}")
                                level_up_message_parts.append(reward["custom_message_on_level_up"])
                            except Exception as e_msg_format:
                                print(f"Inny błąd formatowania wiadomości nagrody: {e_msg_format}")
                                level_up_message_parts.append(reward["custom_message_on_level_up"])

                if awarded_roles_mentions:
                    level_up_message_parts.append(f"Otrzymujesz nowe role: {', '.join(awarded_roles_mentions)}!")

                final_level_up_message = "\n".join(level_up_message_parts)
                await message.channel.send(final_level_up_message)
                print(f"User {message.author.name} leveled up to {calculated_level_xp} on server {message.guild.name}. Nagrody przetworzone.")

            except discord.Forbidden:
                print(f"Nie udało się wysłać wiadomości o awansie/nagrodach na kanale {message.channel.name} (brak uprawnień).")
            except Exception as e_lvl_up:
                print(f"Błąd podczas przetwarzania awansu i nagród dla {message.author.name}: {e_lvl_up}")
    # await bot.process_commands(message)

# --- Komendy Slash ---

# --- Moduł Product Watchlist: Komendy ---
@bot.tree.command(name="watch_product", description="Dodaje produkt do listy śledzenia.")
@app_commands.describe(url_produktu="Pełny link URL do strony produktu (obecnie tylko X-Kom).")
async def watch_product_command(interaction: discord.Interaction, url_produktu: str):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda musi być użyta na serwerze.", ephemeral=True)
        return

    shop_name = None
    if "x-kom.pl" in url_produktu.lower():
        shop_name = "xkom"
    # TODO: Rozbudować o inne sklepy

    if not shop_name:
        await interaction.response.send_message("Nie rozpoznano wspieranego sklepu dla podanego URL. Obecnie tylko X-Kom.", ephemeral=True)
        return

    existing_product = database.get_watched_product_by_url(url_produktu)
    if existing_product and existing_product["is_active"]:
        await interaction.response.send_message(f"Ten produkt ({url_produktu}) jest już aktywnie śledzony.", ephemeral=True)
        return

    product_id = database.add_watched_product(
        user_id=interaction.user.id,
        url=url_produktu,
        shop_name=shop_name,
        guild_id=interaction.guild_id
    )

    if product_id:
        await interaction.response.send_message(f"Produkt został dodany do listy śledzenia (ID: {product_id}). Pierwsze dane pojawią się po kolejnym skanowaniu.", ephemeral=True)
        # Można by tu uruchomić jednorazowe skanowanie dla tego produktu
    else:
        await interaction.response.send_message("Nie udało się dodać produktu. Możliwe, że URL jest już śledzony lub wystąpił błąd.", ephemeral=True)

@bot.tree.command(name="unwatch_product", description="Przestaje śledzić produkt.")
@app_commands.describe(id_produktu="ID produktu z Twojej listy (sprawdź komendą /my_watchlist).")
async def unwatch_product_command(interaction: discord.Interaction, id_produktu: int):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda musi być użyta na serwerze.", ephemeral=True)
        return

    # TODO: Weryfikacja, czy użytkownik jest właścicielem produktu (user_id_who_added) lub adminem
    if database.deactivate_watched_product(id_produktu): # Na razie deaktywuje, nie usuwa całkiem
        await interaction.response.send_message(f"Produkt o ID {id_produktu} został usunięty z aktywnego śledzenia.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Nie znaleziono produktu o ID {id_produktu} na Twojej liście lub już jest nieaktywny.", ephemeral=True)

@bot.tree.command(name="my_watchlist", description="Wyświetla Twoją listę śledzonych produktów na tym serwerze.")
async def my_watchlist_command(interaction: discord.Interaction):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda musi być użyta tylko na serwerze.", ephemeral=True)
        return

    user_products = database.get_user_watched_products(user_id=interaction.user.id, guild_id=interaction.guild_id)

    if not user_products:
        await interaction.response.send_message("Nie śledzisz obecnie żadnych produktów na tym serwerze.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Twoja Lista Śledzonych Produktów na {interaction.guild.name}", color=discord.Color.dark_blue())
    description = ""
    for product in user_products:
        name = product.get('product_name') or "Jeszcze nie zeskanowano nazwy"
        price_cents = product.get('last_known_price_cents')
        price_display = f"{price_cents / 100:.2f} zł" if price_cents is not None else "Brak danych"
        availability = product.get('last_known_availability_str') or "Brak danych"

        description += (f"**ID: {product['id']} | [{name}]({product['product_url']})**\n"
                        f"Sklep: {product['shop_name'].upper()} | Cena: {price_display} | Dostępność: {availability}\n\n")

    if len(description) > 4000: description = description[:3990] + "\n... (lista zbyt długa)"
    embed.description = description if description else "Brak produktów na liście."
    await interaction.response.send_message(embed=embed, ephemeral=True)

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
    if not config: # Powinno być obsłużone przez get_server_config, które zwraca None lub dict z defaultami
        # Jeśli get_server_config zwróci None, to znaczy, że nie ma wpisu dla guild_id, co jest dziwne
        # bo update_server_config powinno go stworzyć. Dla bezpieczeństwa:
        database.update_server_config(interaction.guild_id) # Spróbuj stworzyć domyślny wpis
        config = database.get_server_config(interaction.guild_id)
        if not config: # Jeśli nadal nie ma (błąd krytyczny bazy?)
             await interaction.response.send_message("Błąd odczytu konfiguracji serwera.", ephemeral=True)
             return


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

# --- Zadania w Tle ---
@tasks.loop(hours=4)
async def scan_products_task():
    await bot.wait_until_ready()
    print("[PRODUCT_SCAN_TASK] Rozpoczynam skanowanie produktów...")
    active_products = database.get_all_active_watched_products()
    if not active_products:
        print("[PRODUCT_SCAN_TASK] Brak aktywnych produktów do skanowania.")
        return

    for product in active_products:
        print(f"[PRODUCT_SCAN_TASK] Skanuję: {product['product_url']} (ID: {product['id']})")
        scraped_data = None
        if product['shop_name'] == 'xkom':
            await asyncio.sleep(random.randint(5, 15))
            scraped_data = xkom_scraper.scrape_xkom_product(product['product_url'])

        current_scan_time = int(time.time())
        if scraped_data:
            name = scraped_data.get("name")
            price_cents = scraped_data.get("price_in_cents") # Używamy nowej nazwy klucza
            availability_str = scraped_data.get("availability_str")

            database.update_watched_product_data(
                product_id=product['id'],
                name=name if name else product.get('product_name'),
                price_cents=price_cents, # Przekazujemy cenę w groszach
                availability_str=availability_str,
                scanned_at=current_scan_time
            )
            database.add_price_history_entry(
                watched_product_id=product['id'],
                scan_date=current_scan_time,
                price_cents=price_cents, # Zapisujemy cenę w groszach
                availability_str=availability_str
            )
            price_display = f"{price_cents / 100:.2f} zł" if price_cents is not None else "N/A"
            print(f"[PRODUCT_SCAN_TASK] Zaktualizowano ID {product['id']}: Cena: {price_display}, Dostępność: {availability_str}")
        else:
            print(f"[PRODUCT_SCAN_TASK] Nie udało się zeskanować ID {product['id']}. Zapisuję czas skanowania.")
            database.update_watched_product_data(product_id=product['id'], name=None, price_cents=None, availability_str=None, scanned_at=current_scan_time)
            database.add_price_history_entry(product_id=product['id'], scan_date=current_scan_time, price_cents=None, availability_str="Błąd skanowania")
    print("[PRODUCT_SCAN_TASK] Zakończono skanowanie produktów.")

@tasks.loop(minutes=15)
async def daily_product_report_task():
    await bot.wait_until_ready()
    now_utc = datetime.utcnow()
    guild_configs = database.get_all_guilds_with_product_report_config()

    for config in guild_configs:
        guild_id = config["guild_id"]
        report_channel_id = config.get("report_channel_id") # Użyj .get() dla bezpieczeństwa
        report_time_str = config.get("report_time_utc")

        if not report_channel_id or not report_time_str:
            continue

        today_date_str = now_utc.strftime("%Y-%m-%d")
        if last_report_sent_date.get(guild_id) == today_date_str:
            continue

        try:
            report_hour, report_minute = map(int, report_time_str.split(':'))
            if now_utc.hour == report_hour and now_utc.minute >= report_minute and now_utc.minute < report_minute + 15: # 15-minutowe okno
                guild = bot.get_guild(guild_id)
                if not guild: continue
                report_channel = guild.get_channel(report_channel_id)
                if not report_channel or not isinstance(report_channel, discord.TextChannel):
                    print(f"[REPORT_TASK] Nie znaleziono kanału raportów (ID: {report_channel_id}) na {guild.name}")
                    continue
                print(f"[REPORT_TASK] Generowanie raportu dla {guild.name} (ID: {guild_id})")

                product_changes = database.get_product_changes_for_report(guild_id, hours_ago=24)
                top_drops = database.get_top_price_drops(guild_id, hours_ago=24, limit=5)

                embed = discord.Embed(title=f"📊 Dzienny Raport Produktowy - {now_utc.strftime('%Y-%m-%d')}", color=discord.Color.blue(), timestamp=now_utc)
                embed.set_footer(text=f"Serwer: {guild.name}")
                changes_desc = ""
                if product_changes:
                    for change in product_changes[:10]:
                        name = change.get('product_name', 'Produkt')
                        url = change.get('product_url', '#')
                        old_p_cents = change.get('old_price_cents')
                        new_p_cents = change.get('new_price_cents')
                        old_a = change.get('old_availability_str', 'N/A')
                        new_a = change.get('new_availability_str', 'N/A')

                        old_p_display = f"{old_p_cents / 100:.2f} zł" if old_p_cents is not None else "N/A"
                        new_p_display = f"{new_p_cents / 100:.2f} zł" if new_p_cents is not None else "N/A"

                        price_changed = old_p_cents != new_p_cents and old_p_cents is not None and new_p_cents is not None
                        avail_changed = old_a != new_a and old_a is not None and new_a is not None

                        if price_changed or avail_changed:
                            changes_desc += f"[{name}]({url})\n"
                            if price_changed: changes_desc += f"  Cena: `{old_p_display}` -> `{new_p_display}`\n"
                            if avail_changed: changes_desc += f"  Dostępność: `{old_a}` -> `{new_a}`\n"
                            changes_desc += "\n"
                else: changes_desc = "Brak znaczących zmian cen/dostępności w ciągu ostatnich 24h."
                if len(changes_desc) > 1020: changes_desc = changes_desc[:1017] + "..."
                embed.add_field(name="🔍 Zmiany Cen i Dostępności (24h)", value=changes_desc if changes_desc else "Brak zmian.", inline=False)

                drops_desc = ""
                if top_drops:
                    for i, drop in enumerate(top_drops):
                        name = drop.get('product_name', 'Produkt')
                        url = drop.get('product_url', '#')
                        old_p_cents = drop.get('old_price_cents')
                        new_p_cents = drop.get('new_price_cents')
                        percent = drop.get('drop_percentage', 0)
                        old_p_display = f"{old_p_cents / 100:.2f} zł" if old_p_cents is not None else "N/A"
                        new_p_display = f"{new_p_cents / 100:.2f} zł" if new_p_cents is not None else "N/A"
                        drops_desc += f"{i+1}. [{name}]({url})\n   `{old_p_display}` -> `{new_p_display}` (**-{percent:.1f}%**)\n"
                else: drops_desc = "Brak znaczących spadków cen w ciągu ostatnich 24h."
                if len(drops_desc) > 1020: drops_desc = drops_desc[:1017] + "..."
                embed.add_field(name="📉 Największe Spadki Cen (24h)", value=drops_desc, inline=False)
                embed.add_field(name="📈 Trendy Ogólne", value="Analiza trendów wkrótce!", inline=False)

                try:
                    await report_channel.send(embed=embed)
                    last_report_sent_date[guild_id] = today_date_str
                    print(f"[REPORT_TASK] Wyslano raport dla serwera {guild.name}")
                except discord.Forbidden: print(f"[REPORT_TASK] Brak uprawnień do wysłania raportu na {report_channel.name} ({guild.name})")
                except Exception as e_send: print(f"[REPORT_TASK] Błąd wysyłania raportu dla {guild.name}: {e_send}")
        except ValueError:
            print(f"[REPORT_TASK] Nieprawidłowy format czasu raportu dla serwera ID {guild_id}: '{report_time_str}'")
        except Exception as e_outer:
            print(f"[REPORT_TASK] Ogólny błąd przetwarzania raportu dla serwera ID {guild_id}: {e_outer}")

# (Reszta kodu, definicje innych komend i funkcji pomocniczych)
# ...

if TOKEN:
    bot.run(TOKEN)
else:
    print("Błąd: Nie znaleziono tokena bota w pliku .env")

[end of main.py]
