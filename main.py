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

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Globalny słownik do śledzenia cooldownu XP dla użytkowników
last_xp_gain_timestamp = {}

# Do śledzenia ostatnich wiadomości użytkowników dla filtru spamu
import collections
user_recent_messages = collections.defaultdict(lambda: collections.deque(maxlen=3))

# Do regexów
import re
from utils import time_parser
from datetime import datetime, timedelta

# Scrapery
from scrapers import xkom_scraper # Import naszego scrapera

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_quizzes = {}

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

    if hasattr(bot, 'check_expired_roles') and not check_expired_roles.is_running():
        check_expired_roles.start()
        print("Uruchomiono zadanie 'check_expired_roles'.")
    if hasattr(bot, 'check_expired_punishments_task') and not check_expired_punishments_task.is_running():
        check_expired_punishments_task.start()
        print("Uruchomiono zadanie 'check_expired_punishments_task'.")
    if hasattr(bot, 'check_expired_polls_task') and not check_expired_polls_task.is_running():
        check_expired_polls_task.start()
        print("Uruchomiono zadanie 'check_expired_polls_task'.")
    if hasattr(bot, 'check_ended_giveaways_task') and not check_ended_giveaways_task.is_running():
        check_ended_giveaways_task.start()
        print("Uruchomiono zadanie 'check_ended_giveaways_task'.")
    if hasattr(bot, 'scan_products_task') and not scan_products_task.is_running(): # Dodano start taska
        scan_products_task.start()
        print("Uruchomiono zadanie 'scan_products_task'.")


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
        if server_config.get("filter_profanity_enabled", True):
            banned_words_list = database.get_banned_words(message.guild.id)
            if banned_words_list:
                for banned_word in banned_words_list:
                    pattern = r"(?i)\b" + re.escape(banned_word) + r"\b"
                    if re.search(pattern, message.content):
                        try:
                            await message.delete()
                            await log_moderation_action(message.guild, message.author, message.content, f"Wykryto zakazane słowo: '{banned_word}'", message.channel, server_config.get("moderation_log_channel_id"))
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
                    await log_moderation_action(message.guild, message.author, message.content, "Wykryto link zapraszający Discord.", message.channel, server_config.get("moderation_log_channel_id"))
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
                    await log_moderation_action(message.guild, message.author, message.content, "Wykryto powtarzające się wiadomości (spam).", message.channel, server_config.get("moderation_log_channel_id"))
                    message_deleted_by_moderation = True
                    try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (spam).")
                    except: pass
                except Exception as e: print(f"Błąd auto-moderacji (spam-repeat): {e}")
            if not message_deleted_by_moderation and (len(message.mentions) + len(message.role_mentions) > 5) :
                try:
                    await message.delete()
                    await log_moderation_action(message.guild, message.author, message.content, "Wykryto nadmierną liczbę wzmianek (spam).", message.channel, server_config.get("moderation_log_channel_id"))
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
# ( ... wszystkie poprzednio zdefiniowane komendy slash ... )

# --- Moduł Product Watchlist ---
@bot.tree.command(name="watch_product", description="Dodaje produkt do listy śledzenia cen/dostępności.")
@app_commands.describe(url_produktu="Pełny link URL do strony produktu.")
async def watch_product_command(interaction: discord.Interaction, url_produktu: str):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda musi być użyta na serwerze.", ephemeral=True)
        return

    shop_name = None
    if "x-kom.pl" in url_produktu.lower():
        shop_name = "xkom"

    if not shop_name:
        await interaction.response.send_message("Nie rozpoznano sklepu dla podanego URL. Obecnie wspierany jest tylko X-Kom.", ephemeral=True)
        return

    existing_product = database.get_watched_product_by_url(url_produktu)
    if existing_product and existing_product["is_active"]:
        await interaction.response.send_message(f"Ten produkt ({url_produktu}) jest już śledzony.", ephemeral=True)
        return
    elif existing_product and not existing_product["is_active"]:
        pass # Można by reaktywować, na razie traktujemy jak nowy jeśli nieaktywny

    product_id = database.add_watched_product(
        user_id=interaction.user.id,
        url=url_produktu,
        shop_name=shop_name,
        guild_id=interaction.guild_id
    )

    if product_id:
        await interaction.response.send_message(f"Produkt został dodany do Twojej listy śledzenia (ID: {product_id}). Pierwsze skanowanie danych może chwilę potrwać.", ephemeral=True)
    else:
        await interaction.response.send_message("Nie udało się dodać produktu do listy śledzenia. Możliwe, że jest już śledzony lub wystąpił błąd bazy danych.", ephemeral=True)

@bot.tree.command(name="unwatch_product", description="Usuwa produkt z Twojej listy śledzenia.")
@app_commands.describe(id_produktu="ID produktu z Twojej listy (znajdziesz je komendą /my_watchlist).")
async def unwatch_product_command(interaction: discord.Interaction, id_produktu: int):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda musi być użyta na serwerze.", ephemeral=True)
        return

    # TODO: Sprawdzanie, czy użytkownik jest właścicielem produktu przed deaktywacją
    if database.deactivate_watched_product(id_produktu):
        await interaction.response.send_message(f"Produkt o ID {id_produktu} został usunięty z listy śledzenia (dezaktywowany).", ephemeral=True)
    else:
        await interaction.response.send_message(f"Nie znaleziono aktywnego produktu o ID {id_produktu} do usunięcia.", ephemeral=True)


@bot.tree.command(name="my_watchlist", description="Wyświetla Twoją listę śledzonych produktów na tym serwerze.")
async def my_watchlist_command(interaction: discord.Interaction):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    user_products = database.get_user_watched_products(user_id=interaction.user.id, guild_id=interaction.guild_id)

    if not user_products:
        await interaction.response.send_message("Nie śledzisz obecnie żadnych produktów na tym serwerze. Użyj `/watch_product`, aby dodać.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Twoja Lista Śledzonych Produktów na {interaction.guild.name}", color=discord.Color.dark_blue())

    description_parts = []
    for product in user_products:
        name = product.get('product_name') or "Nieznana nazwa"
        price = product.get('last_known_price_str') or "Brak danych"
        availability = product.get('last_known_availability_str') or "Brak danych"
        line = (f"**ID: {product['id']} | [{name}]({product['product_url']})**\n"
                f"Cena: {price} | Dostępność: {availability}\n")
        description_parts.append(line)

    full_description = "\n".join(description_parts)
    if len(full_description) > 4000:
        full_description = full_description[:3990] + "\n... (więcej produktów na liście)"

    embed.description = full_description
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Zadanie w Tle do Skanowania Produktów ---
@tasks.loop(hours=4) # Przykładowo co 4 godziny
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
            # Dodajemy małe opóźnienie między żądaniami, aby nie obciążać serwera sklepu
            await asyncio.sleep(random.randint(5, 15)) # Losowe opóźnienie 5-15 sekund
            scraped_data = xkom_scraper.scrape_xkom_product(product['product_url'])
        # TODO: Dodać obsługę innych sklepów (elif product['shop_name'] == 'inny_sklep': ...)

        current_scan_time = int(time.time())
        if scraped_data:
            name = scraped_data.get("name")
            price_str = scraped_data.get("price_str")
            availability_str = scraped_data.get("availability_str")

            # Aktualizuj główne dane produktu
            database.update_watched_product_data(
                product_id=product['id'],
                name=name if name else product.get('product_name'), # Użyj starej nazwy, jeśli nowa to None
                price_str=price_str,
                availability_str=availability_str,
                scanned_at=current_scan_time
            )
            # Dodaj wpis do historii
            database.add_price_history_entry(
                watched_product_id=product['id'],
                scan_date=current_scan_time,
                price_str=price_str,
                availability_str=availability_str
            )
            print(f"[PRODUCT_SCAN_TASK] Zaktualizowano produkt ID {product['id']}: Cena: {price_str}, Dostępność: {availability_str}")

            # TODO: Logika powiadomień o zmianie ceny/dostępności
            # Porównaj price_str / availability_str z product['last_known_price_str'] / product['last_known_availability_str']
            # Jeśli jest zmiana, wyślij powiadomienie do użytkownika (user_id_who_added) lub na kanał (guild_id)
            # Np. jeśli cena spadła lub produkt stał się dostępny.

        else:
            print(f"[PRODUCT_SCAN_TASK] Nie udało się zeskanować danych dla produktu ID {product['id']} ({product['product_url']}). Zapisuję tylko czas skanowania.")
            database.update_watched_product_data(product_id=product['id'], name=None, price_str=None, availability_str=None, scanned_at=current_scan_time)
            database.add_price_history_entry(product_id=product['id'], scan_date=current_scan_time, price_str=None, availability_str="Błąd skanowania")


    print("[PRODUCT_SCAN_TASK] Zakończono skanowanie produktów.")


# (Reszta kodu, w tym wszystkie inne komendy i funkcje pomocnicze)
# ...

if TOKEN:
    bot.run(TOKEN)
else:
    print("Błąd: Nie znaleziono tokena bota w pliku .env")

[end of main.py]
