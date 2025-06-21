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

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Globalny słownik do śledzenia cooldownu XP dla użytkowników
# Klucz: (guild_id, user_id), Wartość: timestamp ostatniego przyznania XP
last_xp_gain_timestamp = {}

# Do śledzenia ostatnich wiadomości użytkowników dla filtru spamu
import collections
user_recent_messages = collections.defaultdict(lambda: collections.deque(maxlen=3)) # Przechowuj 3 ostatnie wiadomości

# Do regexów
import re
from utils import time_parser # Nasz parser czasu
from datetime import datetime, timedelta # Do pracy z czasem

# Definiujemy intencje, w tym guilds i members, które mogą być potrzebne
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True # Potrzebne dla on_raw_reaction_add/remove

# Używamy Bot zamiast Client dla łatwiejszej obsługi komend aplikacyjnych
bot = commands.Bot(command_prefix="!", intents=intents)

# Globalny słownik do śledzenia stanu quizu użytkowników
active_quizzes = {}


@bot.event
async def on_ready_final():
    print(f'Zalogowano jako {bot.user}')
    try:
        database.init_db()
        print("Baza danych zainicjalizowana.")
        synced = await bot.tree.sync()
        print(f"Zsynchronizowano {len(synced)} komend(y) globalnie.")
    except Exception as e:
        print(f"Wystąpił błąd podczas synchronizacji komend lub inicjalizacji DB: {e}")

    if hasattr(bot, 'check_expired_roles') and not check_expired_roles.is_running():
        check_expired_roles.start()
        print("Uruchomiono zadanie 'check_expired_roles'.")

    if hasattr(bot, 'check_expired_punishments_task') and not check_expired_punishments_task.is_running():
        check_expired_punishments_task.start()
        print("Uruchomiono zadanie 'check_expired_punishments_task'.")

bot.event(on_ready_final)


# Komenda do ustawiania wiadomości powitalnej
@bot.tree.command(name="set_welcome_message", description="Ustawia treść wiadomości powitalnej dla reakcji.")
@app_commands.describe(tresc="Treść wiadomości powitalnej")
@app_commands.checks.has_permissions(administrator=True)
async def set_welcome_message(interaction: discord.Interaction, tresc: str):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    try:
        database.update_server_config(guild_id=interaction.guild_id, welcome_message_content=tresc)
        await interaction.response.send_message(f"Wiadomość powitalna została ustawiona na: \"{tresc}\"", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd podczas ustawiania wiadomości: {e}", ephemeral=True)

@set_welcome_message.error
async def set_welcome_message_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień do użycia tej komendy.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił nieoczekiwany błąd: {error}", ephemeral=True)

# Komenda do ustawiania roli weryfikacyjnej
@bot.tree.command(name="set_verification_role", description="Ustawia rolę, która będzie nadawana po reakcji.")
@app_commands.describe(rola="Rola do nadania")
@app_commands.checks.has_permissions(administrator=True)
async def set_verification_role(interaction: discord.Interaction, rola: discord.Role):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    try:
        if interaction.guild.me.top_role <= rola:
            await interaction.response.send_message(
                "Nie mogę ustawić tej roli, ponieważ jest ona na tym samym lub wyższym poziomie w hierarchii ról niż moja najwyższa rola. "
                "Upewnij się, że rola bota jest wyżej niż rola, którą próbujesz ustawić.",
                ephemeral=True
            )
            return
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "Nie mam uprawnień do zarządzania rolami na tym serwerze. "
                "Nadaj mi uprawnienie 'Zarządzanie rolami'.",
                ephemeral=True
            )
            return
        database.update_server_config(guild_id=interaction.guild_id, reaction_role_id=rola.id)
        await interaction.response.send_message(f"Rola weryfikacyjna została ustawiona na: {rola.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd podczas ustawiania roli: {e}", ephemeral=True)

@set_verification_role.error
async def set_verification_role_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień do użycia tej komendy.", ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, discord.Forbidden):
        await interaction.response.send_message(
            "Wystąpił błąd uprawnień. Upewnij się, że rola bota jest wyżej w hierarchii niż ustawiana rola "
            "oraz że bot ma uprawnienie 'Zarządzanie rolami'.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(f"Wystąpił nieoczekiwany błąd: {error}", ephemeral=True)

REACTION_EMOJI = "✅"

@bot.tree.command(name="verify", description="Wysyła wiadomość weryfikacyjną, na którą użytkownicy mogą reagować.")
@app_commands.checks.has_permissions(administrator=True)
async def verify_command(interaction: discord.Interaction):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    config = database.get_server_config(interaction.guild_id)
    if not config or not config.get("welcome_message_content") or not config.get("reaction_role_id"):
        await interaction.response.send_message("Konfiguracja dla tego serwera jest niekompletna. Użyj `/set_welcome_message` i `/set_verification_role`.", ephemeral=True)
        return

    welcome_message_content = config["welcome_message_content"]
    reaction_role_id = config["reaction_role_id"]
    role_to_assign = interaction.guild.get_role(reaction_role_id)

    if not role_to_assign:
        await interaction.response.send_message(f"Skonfigurowana rola (ID: {reaction_role_id}) nie została znaleziona. Sprawdź konfigurację.", ephemeral=True)
        return

    if interaction.channel is None or not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("Tej komendy można użyć tylko na kanale tekstowym.", ephemeral=True)
        return

    await interaction.response.send_message("Przygotowuję wiadomość weryfikacyjną...", ephemeral=True)
    try:
        reaction_message = await interaction.channel.send(content=welcome_message_content)
        await reaction_message.add_reaction(REACTION_EMOJI)
        database.update_server_config(guild_id=interaction.guild_id, reaction_message_id=reaction_message.id)
        await interaction.followup.send(f"Wiadomość weryfikacyjna została wysłana. ID: {reaction_message.id}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Nie mam uprawnień do wysłania wiadomości lub dodania reakcji na tym kanale.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Wystąpił błąd: {e}", ephemeral=True)

@verify_command.error
async def verify_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.member is None or payload.member.bot: return
    if str(payload.emoji) != REACTION_EMOJI: return

    config = database.get_server_config(payload.guild_id)
    if not (config and config.get("reaction_message_id") == payload.message_id and config.get("reaction_role_id")):
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild: return

    role_id = config["reaction_role_id"]
    role_to_assign = guild.get_role(role_id)
    if not role_to_assign:
        print(f"Błąd (on_raw_reaction_add): Rola {role_id} nie znaleziona na serwerze {guild.name}")
        return

    member = guild.get_member(payload.user_id)
    if not member: return

    if guild.me.top_role <= role_to_assign or not guild.me.guild_permissions.manage_roles:
        print(f"Ostrzeżenie (on_raw_reaction_add): Bot nie może nadać roli {role_to_assign.name} (hierarchia/uprawnienia) na {guild.name}")
        return

    if role_to_assign not in member.roles:
        try:
            await member.add_roles(role_to_assign, reason="Reakcja na wiadomość weryfikacyjną")
            print(f"Nadano rolę {role_to_assign.name} użytkownikowi {member.name}")
            try:
                await member.send(f"Otrzymałeś/aś rolę **{role_to_assign.name}** na serwerze **{guild.name}**.")
            except discord.Forbidden: pass
        except discord.Forbidden:
            print(f"Błąd (on_raw_reaction_add): Brak uprawnień do nadania roli {role_to_assign.name} użytkownikowi {member.name}")
        except Exception as e:
            print(f"Nieoczekiwany błąd (on_raw_reaction_add): {e}")

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) != REACTION_EMOJI: return

    guild = bot.get_guild(payload.guild_id)
    if not guild: return

    member = guild.get_member(payload.user_id)
    if not member or member.bot: return

    config = database.get_server_config(payload.guild_id)
    if not (config and config.get("reaction_message_id") == payload.message_id and config.get("reaction_role_id")):
        return

    role_id = config["reaction_role_id"]
    role_to_remove = guild.get_role(role_id)
    if not role_to_remove:
        print(f"Błąd (on_raw_reaction_remove): Rola {role_id} nie znaleziona na serwerze {guild.name}")
        return

    if guild.me.top_role <= role_to_remove or not guild.me.guild_permissions.manage_roles:
        print(f"Ostrzeżenie (on_raw_reaction_remove): Bot nie może odebrać roli {role_to_remove.name} (hierarchia/uprawnienia) na {guild.name}")
        return

    if role_to_remove in member.roles:
        try:
            await member.remove_roles(role_to_remove, reason="Usunięcie reakcji z wiadomości weryfikacyjnej")
            print(f"Odebrano rolę {role_to_remove.name} użytkownikowi {member.name}")
            try:
                await member.send(f"Twoja rola **{role_to_remove.name}** na serwerze **{guild.name}** została usunięta.")
            except discord.Forbidden: pass
        except discord.Forbidden:
            print(f"Błąd (on_raw_reaction_remove): Brak uprawnień do odebrania roli {role_to_remove.name} użytkownikowi {member.name}")
        except Exception as e:
            print(f"Nieoczekiwany błąd (on_raw_reaction_remove): {e}")


# --- Role Czasowe ---
@bot.tree.command(name="temprole", description="Nadaje użytkownikowi rolę na określony czas.")
@app_commands.describe(uzytkownik="Użytkownik, któremu nadać rolę", rola="Rola do nadania", czas="Czas trwania roli (liczba)", jednostka="Jednostka czasu (minuty, godziny, dni)")
@app_commands.choices(jednostka=[app_commands.Choice(name="Minuty",value="minuty"), app_commands.Choice(name="Godziny",value="godziny"), app_commands.Choice(name="Dni",value="dni")])
@app_commands.checks.has_permissions(manage_roles=True)
async def temprole_command(interaction: discord.Interaction, uzytkownik: discord.Member, rola: discord.Role, czas: int, jednostka: app_commands.Choice[str] = None):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    actual_jednostka = jednostka.value if jednostka else "minuty"
    if czas <= 0:
        await interaction.response.send_message("Czas trwania musi być dodatni.", ephemeral=True)
        return

    duration_seconds = 0
    if actual_jednostka == "minuty": duration_seconds = czas * 60
    elif actual_jednostka == "godziny": duration_seconds = czas * 3600
    elif actual_jednostka == "dni": duration_seconds = czas * 86400
    else:
        await interaction.response.send_message("Nieprawidłowa jednostka czasu.", ephemeral=True)
        return

    if interaction.guild.me.top_role <= rola or not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("Nie mogę nadać tej roli (hierarchia lub brak uprawnień 'Zarządzanie Rolami').", ephemeral=True)
        return

    active_role_info = database.get_active_timed_role(interaction.guild_id, uzytkownik.id, rola.id)
    if active_role_info:
        exp_ts = active_role_info['expiration_timestamp']
        await interaction.response.send_message(f"{uzytkownik.mention} ma już rolę {rola.mention} (wygasa <t:{exp_ts}:R>).", ephemeral=True)
        return

    expiration_timestamp = int(time.time() + duration_seconds)
    try:
        await uzytkownik.add_roles(rola, reason=f"Czasowo przez {interaction.user.name} ({czas} {actual_jednostka})")
        database.add_timed_role(interaction.guild_id, uzytkownik.id, rola.id, expiration_timestamp)
        exp_readable = f"<t:{expiration_timestamp}:F> (<t:{expiration_timestamp}:R>)"
        await interaction.response.send_message(f"Nadano {rola.mention} dla {uzytkownik.mention} na {czas} {actual_jednostka}. Wygasa: {exp_readable}.",ephemeral=True)
        try:
            await uzytkownik.send(f"Otrzymałeś/aś rolę **{rola.name}** na **{interaction.guild.name}** na {czas} {actual_jednostka}. Wygasa: {exp_readable}.")
        except discord.Forbidden: pass
    except discord.Forbidden:
        await interaction.response.send_message("Błąd uprawnień przy nadawaniu roli.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Nieoczekiwany błąd: {e}", ephemeral=True)
        print(f"Błąd w /temprole: {e}")

@temprole_command.error
async def temprole_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Brak uprawnień (Zarządzanie Rolami).", ephemeral=True)
    else:
        if not interaction.response.is_done(): await interaction.response.send_message(f"Błąd: {error}", ephemeral=True)
        else: await interaction.followup.send(f"Błąd: {error}", ephemeral=True)
        print(f"Błąd w temprole_command_error: {error}")

@tasks.loop(seconds=60)
async def check_expired_roles():
    await bot.wait_until_ready()
    current_timestamp = int(time.time())
    expired_entries = database.get_expired_roles(current_timestamp)
    for entry in expired_entries:
        entry_id, guild_id, user_id, role_id, _ = entry
        guild = bot.get_guild(guild_id)
        if not guild:
            database.remove_timed_role(entry_id)
            continue
        role = guild.get_role(role_id)
        member = guild.get_member(user_id)
        if not role or not member:
            database.remove_timed_role(entry_id)
            continue
        if guild.me.top_role > role and guild.me.guild_permissions.manage_roles:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="Rola czasowa wygasła")
                    print(f"Automatycznie zdjęto rolę {role.name} z {member.name}")
                    try:
                        await member.send(f"Twoja rola czasowa **{role.name}** na **{guild.name}** wygasła.")
                    except discord.Forbidden: pass
                except Exception as e:
                    print(f"Błąd przy auto-usuwaniu roli {role.name} z {member.name}: {e}")
        else:
            print(f"Bot nie może auto-usunąć roli {role.name} z {member.name} (hierarchia/uprawnienia). Wpis {entry_id} pozostaje.")
            continue
        database.remove_timed_role(entry_id)


# --- Role za Aktywność ---
@bot.tree.command(name="add_activity_role", description="Dodaje konfigurację roli za aktywność (liczbę wiadomości).")
@app_commands.describe(rola="Rola do nadania", liczba_wiadomosci="Wymagana liczba wiadomości")
@app_commands.checks.has_permissions(administrator=True)
async def add_activity_role_command(interaction: discord.Interaction, rola: discord.Role, liczba_wiadomosci: int):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    if liczba_wiadomosci <= 0:
        await interaction.response.send_message("Liczba wiadomości musi być dodatnia.", ephemeral=True)
        return
    if interaction.guild.me.top_role <= rola or not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("Nie mogę zarządzać tą rolą (hierarchia/brak uprawnień).", ephemeral=True)
        return
    try:
        database.add_activity_role_config(interaction.guild_id, rola.id, liczba_wiadomosci)
        await interaction.response.send_message(f"Skonfigurowano rolę {rola.mention} za {liczba_wiadomosci} wiadomości.", ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.response.send_message("Ta rola lub próg wiadomości jest już skonfigurowany.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Nieoczekiwany błąd: {e}", ephemeral=True)

@add_activity_role_command.error
async def add_activity_role_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions): await interaction.response.send_message("Brak uprawnień administratora.", ephemeral=True)
    else:
        if not interaction.response.is_done(): await interaction.response.send_message(f"Błąd: {error}", ephemeral=True)
        else: await interaction.followup.send(f"Błąd: {error}", ephemeral=True)

@bot.tree.command(name="remove_activity_role", description="Usuwa konfigurację roli za aktywność.")
@app_commands.describe(rola="Rola, której konfigurację usunąć")
@app_commands.checks.has_permissions(administrator=True)
async def remove_activity_role_command(interaction: discord.Interaction, rola: discord.Role):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    if database.remove_activity_role_config(interaction.guild_id, rola.id):
        await interaction.response.send_message(f"Usunięto konfigurację dla {rola.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Rola {rola.mention} nie była skonfigurowana.", ephemeral=True)

@remove_activity_role_command.error
async def remove_activity_role_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions): await interaction.response.send_message("Brak uprawnień administratora.", ephemeral=True)
    else:
        if not interaction.response.is_done(): await interaction.response.send_message(f"Błąd: {error}", ephemeral=True)
        else: await interaction.followup.send(f"Błąd: {error}", ephemeral=True)

@bot.tree.command(name="list_activity_roles", description="Wyświetla skonfigurowane role za aktywność.")
async def list_activity_roles_command(interaction: discord.Interaction):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    configs = database.get_activity_role_configs(interaction.guild_id)
    if not configs:
        await interaction.response.send_message("Brak skonfigurowanych ról za aktywność.", ephemeral=True)
        return
    embed = discord.Embed(title="Role za Aktywność", color=discord.Color.blue())
    description = "\n".join([f"{interaction.guild.get_role(c['role_id']).mention if interaction.guild.get_role(c['role_id']) else f'ID: {c['role_id']}'} - {c['required_message_count']} wiadomości" for c in configs])
    embed.description = description
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Event `on_message` (nazwa zmieniona na `on_message_with_quiz_and_more`) ---
@bot.event # Dodajemy dekorator @bot.event
async def on_message_with_quiz_and_more(message: discord.Message): # Zmieniona nazwa
    # 1. Obsługa odpowiedzi na quiz w DM
    if isinstance(message.channel, discord.DMChannel) and message.author.id in active_quizzes and not message.author.bot:
        user_id_quiz = message.author.id
        quiz_state = active_quizzes[user_id_quiz]
        if quiz_state["current_q_index"] < len(quiz_state["questions"]):
            quiz_state["answers"].append(message.content)
            quiz_state["current_q_index"] += 1
            await send_quiz_question_dm(message.author)
        return # Zakończ przetwarzanie dla odpowiedzi na quiz

    # 2. Ignoruj boty i wiadomości prywatne (jeśli nie były odpowiedzią na quiz) dla dalszych akcji
    if message.author.bot or not message.guild:
        return

    # 3. Logika Moderacji (jeśli wiadomość z serwera i nie od bota)
    message_deleted_by_moderation = False
    server_config_mod = database.get_server_config(message.guild.id)
    if server_config_mod: # Tylko jeśli jest jakakolwiek konfiguracja serwera
        # Filtr Wulgaryzmów
        if server_config_mod.get("filter_profanity_enabled", True):
            banned_words_list = database.get_banned_words(message.guild.id)
            if banned_words_list:
                for banned_word in banned_words_list:
                    pattern = r"(?i)\b" + re.escape(banned_word) + r"\b"
                    if re.search(pattern, message.content):
                        try:
                            await message.delete()
                            await log_moderation_action(message.guild, message.author, message.content, f"Wykryto zakazane słowo: '{banned_word}'", message.channel, server_config_mod.get("moderation_log_channel_id"))
                            message_deleted_by_moderation = True
                            try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (niedozwolone słownictwo).")
                            except: pass
                        except Exception as e: print(f"Błąd auto-moderacji (profanity): {e}")
                        break
        # Filtr Linków Zapraszających
        if not message_deleted_by_moderation and server_config_mod.get("filter_invites_enabled", True):
            invite_pattern = r"(discord\.(gg|me|io|com\/invite)\/[a-zA-Z0-9]+)"
            if re.search(invite_pattern, message.content, re.IGNORECASE):
                try:
                    await message.delete()
                    await log_moderation_action(message.guild, message.author, message.content, "Wykryto link zapraszający Discord.", message.channel, server_config_mod.get("moderation_log_channel_id"))
                    message_deleted_by_moderation = True
                    try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (linki zapraszające).")
                    except: pass
                except Exception as e: print(f"Błąd auto-moderacji (invites): {e}")
        # Filtr Spamu
        if not message_deleted_by_moderation and server_config_mod.get("filter_spam_enabled", True):
            user_msgs = user_recent_messages[message.author.id]
            user_msgs.append(message.content)
            if len(user_msgs) == user_msgs.maxlen and len(set(user_msgs)) == 1:
                try:
                    await message.delete()
                    await log_moderation_action(message.guild, message.author, message.content, "Wykryto powtarzające się wiadomości (spam).", message.channel, server_config_mod.get("moderation_log_channel_id"))
                    message_deleted_by_moderation = True
                    try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (spam).")
                    except: pass
                except Exception as e: print(f"Błąd auto-moderacji (spam-repeat): {e}")
            if not message_deleted_by_moderation and (len(message.mentions) + len(message.role_mentions) > 5) :
                try:
                    await message.delete()
                    await log_moderation_action(message.guild, message.author, message.content, "Wykryto nadmierną liczbę wzmianek (spam).", message.channel, server_config_mod.get("moderation_log_channel_id"))
                    message_deleted_by_moderation = True
                    try: await message.author.send(f"Twoja wiadomość na **{message.guild.name}** została usunięta (nadmierne wzmianki).")
                    except: pass
                except Exception as e: print(f"Błąd auto-moderacji (spam-mentions): {e}")

    if message_deleted_by_moderation:
        return # Nie przetwarzaj dalej dla XP itp.

    # 4. Logika XP i Poziomów (jeśli wiadomość nie została usunięta)
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
                # Wiadomość o awansie - początek
                level_up_message_parts = [f"🎉 Gratulacje {message.author.mention}! Osiągnąłeś/aś **Poziom {calculated_level_xp}**!"]

                # Pobierz i przyznaj nagrody za poziom
                level_rewards = database.get_rewards_for_level(guild_id, calculated_level_xp)
                awarded_roles_mentions = [] # Lista do zbierania wzmianek nadanych ról

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

    # 5. Obsługa komend tekstowych (jeśli są) - powinna być na końcu, jeśli wiadomość nie została usunięta i nie była odpowiedzią na quiz.
    # await bot.process_commands(message)

bot.on_message(on_message_with_quiz_and_more) # Rejestracja nowego handlera on_message


# Komenda /rank
@bot.tree.command(name="rank", description="Wyświetla Twój aktualny poziom i postęp XP (lub innego użytkownika).")
@app_commands.describe(uzytkownik="Użytkownik, którego statystyki chcesz zobaczyć (opcjonalnie).")
async def rank_command(interaction: discord.Interaction, uzytkownik: discord.Member = None):
    if not interaction.guild_id or not interaction.guild: # Dodane sprawdzenie guild
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    target_user = uzytkownik if uzytkownik else interaction.user
    if not isinstance(target_user, discord.Member): # Upewnij się, że to Member
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
        xp_display = f"{xp_in_current_level} / {xp_needed_for_level_up_from_current} XP na tym poziomie (Całkowite: {current_xp})"
    elif current_level == 0 and xp_for_next_level_gate > 0 : # Specjalny przypadek dla poziomu 0
        progress_percentage = (current_xp / xp_for_next_level_gate) * 100
        filled_blocks = int(progress_percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "█" * filled_blocks + "░" * empty_blocks
        xp_display = f"{current_xp} / {xp_for_next_level_gate} XP (Całkowite: {current_xp})"


    embed = discord.Embed(title=f"Statystyki Aktywności dla {target_user.display_name}", color=discord.Color.green() if target_user == interaction.user else discord.Color.blue())
    embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="Poziom", value=f"**{current_level}**", inline=True)
    embed.add_field(name="Całkowite XP", value=f"**{current_xp}**", inline=True)

    rank_info = database.get_user_rank_in_server(interaction.guild_id, target_user.id)
    rank_display = "Brak w rankingu (0 XP)"
    if rank_info:
        rank_display = f"#{rank_info[0]} z {rank_info[1]}"
    embed.add_field(name="Ranking Serwera", value=rank_display, inline=True)

    embed.add_field(name=f"Postęp do Poziomu {current_level + 1}", value=f"{progress_bar} ({progress_percentage:.2f}%)\n{xp_display}", inline=False)
    await interaction.response.send_message(embed=embed)

# --- System Weryfikacji Quizem --- (reszta kodu bez zmian)
# ... (cała reszta kodu aż do końca pliku)
[end of main.py]

[end of main.py]
