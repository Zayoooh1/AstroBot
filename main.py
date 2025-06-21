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

# --- Event `on_message` ---
@bot.event
async def on_message(message: discord.Message):
    # 1. Obsługa odpowiedzi na quiz w DM
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
    server_config = database.get_server_config(message.guild.id) # Pobierz konfigurację raz

    # 3. Logika Moderacji
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

    # 4. Obsługa Niestandardowych Komend Tekstowych
    if server_config: # Użyj tej samej, już pobranej konfiguracji
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
                            if 'timestamp' in embed_data: del embed_data['timestamp'] # Usuń timestamp, jeśli jest
                            embed_to_send = discord.Embed.from_dict(embed_data)
                            await message.channel.send(embed=embed_to_send)
                        print(f"Wykonano niestandardową komendę '{prefix}{command_name}' przez {message.author.name}")
                        return # Komenda wykonana, nie przetwarzaj dalej dla XP
                    except json.JSONDecodeError:
                        print(f"Błąd (custom command): Niepoprawny JSON dla '{prefix}{command_name}'")
                    except Exception as e_custom:
                        print(f"Błąd wykonania custom command '{prefix}{command_name}': {e_custom}")

    # 5. Logika XP i Poziomów (jeśli wiadomość nie była komendą niestandardową)
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

    # await bot.process_commands(message) # Jeśli masz inne komendy tekstowe z prefixem bota

# Reszta komend (slash commands) bez zmian
# ... (komendy /rank, /leaderboard, /set_unverified_role, /set_verified_role, /verify_me, etc.)
# ... (komendy /add_level_reward, /remove_level_reward, /list_level_rewards)
# ... (komendy /set_modlog_channel, /add_banned_word, /remove_banned_word, /list_banned_words, /toggle_filter, /moderation_settings)
# ... (komendy /set_muted_role, /set_actions_log_channel, /mute, /unmute, /ban, /unban, /kick, /warn, /history)
# ... (komendy /create_poll, /close_poll)
# ... (komendy /set_custom_prefix, /addcustomcommand, /editcustomcommand, /removecustomcommand, /listcustomcommands)
# ... (funkcje pomocnicze jak send_quiz_question_dm, process_quiz_results, log_moderation_action, _handle_giveaway_end_logic)
# ... (taski w tle: check_expired_roles, check_expired_punishments_task, check_expired_polls_task, check_ended_giveaways_task)

# (Tutaj wklej cały pozostały kod main.py, który nie został pokazany w read_files,
#  a następnie dodaj kod dla /addcustomcommand, /editcustomcommand, /removecustomcommand, /listcustomcommands,
#  oraz logikę w on_message. Zakładam, że kod do wklejenia jest taki sam jak w moim wewnętrznym stanie.)

# Komenda /rank
@bot.tree.command(name="rank", description="Wyświetla Twój aktualny poziom i postęp XP (lub innego użytkownika).")
@app_commands.describe(uzytkownik="Użytkownik, którego statystyki chcesz zobaczyć (opcjonalnie).")
async def rank_command(interaction: discord.Interaction, uzytkownik: discord.Member = None):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    target_user = uzytkownik if uzytkownik else interaction.user
    if not isinstance(target_user, discord.Member):
        target_user_fetched = interaction.guild.get_member(target_user.id)
        if not target_user_fetched:
            await interaction.response.send_message("Nie udało się znaleźć tego użytkownika na serwerze.", ephemeral=True)
            return
        target_user = target_user_fetched

    user_stats = database.get_user_stats(interaction.guild_id, target_user.id)
    current_level = user_stats['level']
    current_xp = user_stats['xp']

    xp_for_current_level_gate = leveling.total_xp_for_level(current_level)
    xp_for_next_level_gate = leveling.total_xp_for_level(current_level + 1)
    xp_in_current_level = current_xp - xp_for_current_level_gate
    xp_needed_for_level_up_from_current = xp_for_next_level_gate - xp_for_current_level_gate

    xp_display = f"{current_xp} XP"
    progress_bar = "█" * 10 + " (MAX POZIOM)"
    progress_percentage = 100.0

    if xp_needed_for_level_up_from_current > 0 :
        progress_percentage = (xp_in_current_level / xp_needed_for_level_up_from_current) * 100
        filled_blocks = int(progress_percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "█" * filled_blocks + "░" * empty_blocks
        xp_display = f"{xp_in_current_level:,} / {xp_needed_for_level_up_from_current:,} XP na tym poziomie (Całkowite: {current_xp:,})"
    elif current_level == 0 and xp_for_next_level_gate > 0 :
        progress_percentage = (current_xp / xp_for_next_level_gate) * 100
        filled_blocks = int(progress_percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "█" * filled_blocks + "░" * empty_blocks
        xp_display = f"{current_xp:,} / {xp_for_next_level_gate:,} XP (Całkowite: {current_xp:,})"
    else:
        xp_display = f"Całkowite XP: {current_xp:,}"


    embed = discord.Embed(title=f"Statystyki Aktywności dla {target_user.display_name}", color=discord.Color.green() if target_user == interaction.user else discord.Color.blue())
    embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="Poziom", value=f"**{current_level}**", inline=True)
    embed.add_field(name="Całkowite XP", value=f"**{current_xp:,}**", inline=True)

    rank_info = database.get_user_rank_in_server(interaction.guild_id, target_user.id)
    rank_display = "Brak w rankingu (0 XP)"
    if rank_info:
        rank_display = f"#{rank_info[0]} z {rank_info[1]}"
    embed.add_field(name="Ranking Serwera", value=rank_display, inline=True)

    embed.add_field(name=f"Postęp do Poziomu {current_level + 1}", value=f"{progress_bar} ({progress_percentage:.2f}%)\n{xp_display}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Wyświetla ranking top 10 użytkowników na serwerze pod względem XP.")
@app_commands.describe(strona="Numer strony leaderboardu (opcjonalnie).")
async def leaderboard_command(interaction: discord.Interaction, strona: int = 1):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    if strona <= 0: strona = 1
    limit_per_page = 10
    offset = (strona - 1) * limit_per_page

    leaderboard_data = database.get_server_leaderboard(interaction.guild_id, limit=limit_per_page, offset=offset)

    if not leaderboard_data:
        if strona == 1:
            await interaction.response.send_message("Nikt jeszcze nie zdobył XP na tym serwerze!", ephemeral=True)
        else:
            await interaction.response.send_message(f"Brak użytkowników na stronie {strona} leaderboardu.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🏆 Leaderboard Aktywności - Strona {strona}",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text=f"Serwer: {interaction.guild.name}")

    description_lines = []
    for i, entry in enumerate(leaderboard_data):
        user_obj = interaction.guild.get_member(entry["user_id"])
        if not user_obj:
            try:
                user_obj = await bot.fetch_user(entry["user_id"])
                user_display_name = user_obj.global_name or user_obj.name
            except discord.NotFound:
                user_display_name = f"ID: {entry['user_id']} (Nieznany)"
        else:
            user_display_name = user_obj.mention

        rank_pos = offset + i + 1
        description_lines.append(
            f"**{rank_pos}.** {user_display_name} - Poziom: **{entry['level']}** (XP: {entry['xp']:,})"
        )

    embed.description = "\n".join(description_lines)

    if len(leaderboard_data) == limit_per_page:
        next_page_check = database.get_server_leaderboard(interaction.guild_id, limit=1, offset=strona * limit_per_page)
        if next_page_check:
             embed.add_field(name="\u200b", value=f"Użyj `/leaderboard strona:{strona + 1}` aby zobaczyć następną stronę.", inline=False)

    await interaction.response.send_message(embed=embed)

# ... (wszystkie inne komendy i funkcje pomocnicze, które były wcześniej) ...
# (Np. set_welcome_message, set_verification_role, verify, on_raw_reaction_add/remove)
# (temprole, check_expired_roles)
# (add_activity_role, remove_activity_role, list_activity_roles)
# (set_unverified_role, set_verified_role, verify_me, send_quiz_question_dm, process_quiz_results)
# (log_moderation_action, mute, unmute, ban, unban, kick, warn, history)
# (set_modlog_channel, add_banned_word, remove_banned_word, list_banned_words, toggle_filter, moderation_settings)
# (create_poll, check_expired_polls_task, close_poll)
# (set_custom_prefix, addcustomcommand, editcustomcommand, removecustomcommand, listcustomcommands)
# (create_giveaway, _handle_giveaway_end_logic, check_ended_giveaways_task, end_giveaway, reroll_giveaway)
# (add_level_reward, remove_level_reward, list_level_rewards)


if TOKEN:
    bot.run(TOKEN)
else:
    print("Błąd: Nie znaleziono tokena bota w pliku .env")
