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


# --- Główny Event On Ready ---
@bot.event
async def on_ready(): # Zmieniono nazwę z on_ready_final/on_ready_setup na standardowe on_ready
    print(f'Zalogowano jako {bot.user}')
    try:
        database.init_db()
        print("Baza danych zainicjalizowana.")
        synced = await bot.tree.sync() # Synchronizuj globalnie
        print(f"Zsynchronizowano {len(synced)} komend(y) globalnie.")
    except Exception as e:
        print(f"Wystąpił błąd podczas inicjalizacji lub synchronizacji komend: {e}")

    # Startuj wszystkie taski w tle, jeśli jeszcze nie działają
    if hasattr(bot, 'check_expired_roles') and not check_expired_roles.is_running():
        check_expired_roles.start()
        print("Uruchomiono zadanie 'check_expired_roles'.")

    if hasattr(bot, 'check_expired_punishments_task') and not check_expired_punishments_task.is_running():
        check_expired_punishments_task.start()
        print("Uruchomiono zadanie 'check_expired_punishments_task'.")

    if hasattr(bot, 'check_expired_polls_task') and not check_expired_polls_task.is_running():
        check_expired_polls_task.start()
        print("Uruchomiono zadanie 'check_expired_polls_task'.")

    if hasattr(bot, 'check_ended_giveaways_task') and not check_ended_giveaways_task.is_running(): # Nowy task dla konkursów
        check_ended_giveaways_task.start()
        print("Uruchomiono zadanie 'check_ended_giveaways_task'.")


# --- Moduł Konkursów (Giveaways) ---
GIVEAWAY_REACTION_EMOJI = "🎉"

@bot.tree.command(name="create_giveaway", description="Tworzy nowy konkurs (giveaway).")
@app_commands.describe(
    nagroda="Co jest do wygrania?",
    liczba_zwyciezcow="Ilu będzie zwycięzców (domyślnie 1).",
    czas_trwania="Jak długo trwa konkurs (np. 1d, 12h, 30m).",
    kanal="Na którym kanale opublikować konkurs (domyślnie aktualny).",
    wymagana_rola="Rola wymagana do udziału (opcjonalnie).",
    minimalny_poziom="Minimalny poziom aktywności wymagany do udziału (opcjonalnie)."
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_giveaway_command(
    interaction: discord.Interaction,
    nagroda: str,
    czas_trwania: str,
    liczba_zwyciezcow: int = 1,
    kanal: discord.TextChannel = None,
    wymagana_rola: discord.Role = None,
    minimalny_poziom: int = None
):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    target_channel = kanal if kanal else interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("Konkurs może być opublikowany tylko na kanale tekstowym.", ephemeral=True)
        return

    if liczba_zwyciezcow < 1:
        await interaction.response.send_message("Liczba zwycięzców musi wynosić co najmniej 1.", ephemeral=True)
        return

    duration_seconds = time_parser.parse_duration(czas_trwania)
    if duration_seconds is None or duration_seconds <= 0:
        await interaction.response.send_message("Nieprawidłowy format czasu trwania lub czas jest zbyt krótki. Użyj np. 30m, 2h, 1d.", ephemeral=True)
        return

    ends_at_timestamp = int(time.time() + duration_seconds)

    try:
        giveaway_id = database.create_giveaway(
            guild_id=interaction.guild_id,
            channel_id=target_channel.id,
            prize=nagroda,
            winner_count=liczba_zwyciezcow,
            created_by_id=interaction.user.id,
            ends_at=ends_at_timestamp,
            required_role_id=wymagana_rola.id if wymagana_rola else None,
            min_level=minimalny_poziom
        )
        if giveaway_id is None:
            await interaction.response.send_message("Nie udało się utworzyć konkursu w bazie danych.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎉 KONKURS: {nagroda} 🎉",
            description=f"Zareaguj {GIVEAWAY_REACTION_EMOJI} aby wziąć udział!",
            color=discord.Color.gold(),
            timestamp=datetime.utcfromtimestamp(ends_at_timestamp)
        )
        embed.add_field(name="Nagroda", value=nagroda, inline=False)
        embed.add_field(name="Liczba zwycięzców", value=str(liczba_zwyciezcow), inline=True)
        embed.add_field(name="Koniec", value=f"<t:{ends_at_timestamp}:R> (<t:{ends_at_timestamp}:F>)", inline=True)

        conditions = []
        if wymagana_rola:
            conditions.append(f"- Musisz posiadać rolę: {wymagana_rola.mention}")
        if minimalny_poziom is not None and minimalny_poziom > 0:
            conditions.append(f"- Musisz posiadać co najmniej: Poziom {minimalny_poziom}")

        if conditions:
            embed.add_field(name="Warunki udziału", value="\n".join(conditions), inline=False)

        embed.set_footer(text=f"Konkurs stworzony przez {interaction.user.display_name} | ID Konkursu: {giveaway_id}")

        giveaway_message = await target_channel.send(embed=embed)
        database.set_giveaway_message_id(giveaway_id, giveaway_message.id)
        await giveaway_message.add_reaction(GIVEAWAY_REACTION_EMOJI)

        await interaction.response.send_message(f"Konkurs na \"{nagroda}\" został pomyślnie utworzony na kanale {target_channel.mention}!", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message(f"Nie mam uprawnień do wysłania wiadomości lub dodania reakcji na kanale {target_channel.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił nieoczekiwany błąd podczas tworzenia konkursu: {e}", ephemeral=True)
        print(f"Błąd w /create_giveaway: {e}")

@create_giveaway_command.error
async def create_giveaway_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień do zarządzania serwerem, aby utworzyć konkurs.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"Wystąpił błąd: {error}", ephemeral=True)
        print(f"Błąd w create_giveaway_error: {error}")

# --- Wspólna logika kończenia konkursu ---
async def _handle_giveaway_end_logic(guild: discord.Guild,
                                   giveaway_data: dict,
                                   giveaway_message: discord.Message,
                                   is_manual_end: bool = False,
                                   reroll_target_user: discord.Member | None = None,
                                   num_to_reroll: int = 1):
    channel = guild.get_channel(giveaway_data["channel_id"])
    if not channel or not isinstance(channel, discord.TextChannel):
        print(f"[GIVEAWAY_LOGIC] Błąd: Kanał {giveaway_data['channel_id']} nie istnieje lub nie jest tekstowy.")
        database.end_giveaway(giveaway_data["id"], [])
        return None, "Nie znaleziono kanału konkursu."

    reaction_to_check = discord.utils.get(giveaway_message.reactions, emoji=GIVEAWAY_REACTION_EMOJI)

    participants_users = []
    if reaction_to_check:
        async for user_obj in reaction_to_check.users():
            if not user_obj.bot:
                member = guild.get_member(user_obj.id)
                if member: participants_users.append(member)

    eligible_participants = []
    if participants_users:
        required_role_id = giveaway_data.get("required_role_id")
        min_level = giveaway_data.get("min_level")
        for member in participants_users:
            eligible = True
            if required_role_id:
                role = guild.get_role(required_role_id)
                if not role or role not in member.roles: eligible = False
            if eligible and min_level is not None and min_level > 0:
                user_stats = database.get_user_stats(guild.id, member.id)
                if user_stats['level'] < min_level: eligible = False
            if eligible: eligible_participants.append(member)

    winners = []
    winner_ids = []
    action_type_log_suffix = ""

    current_winners_ids = giveaway_data.get("winners_json") or []

    if reroll_target_user:
        if reroll_target_user.id not in current_winners_ids:
            return None, f"{reroll_target_user.mention} nie był/a jednym z pierwotnych zwycięzców."

        eligible_for_reroll = [p for p in eligible_participants if p.id != reroll_target_user.id and p.id not in current_winners_ids]
        if not eligible_for_reroll:
            return None, "Brak kwalifikujących się uczestników do ponownego losowania (poza obecnymi zwycięzcami i celem rerolla)."

        new_winner = random.choice(eligible_for_reroll)
        winners = [new_winner]
        winner_ids = [new_winner.id]

        updated_winner_ids = [w_id if w_id != reroll_target_user.id else new_winner.id for w_id in current_winners_ids]
        database.end_giveaway(giveaway_data["id"], updated_winner_ids) # Nadpisz listę zwycięzców
        action_type_log_suffix = f" (Reroll: {reroll_target_user.name} -> {new_winner.name})"
        results_title = f"🔄 REROLL Konkursu: {giveaway_data['prize']} 🔄"
        results_message_content = f"Nowy zwycięzca w konkursie na **{giveaway_data['prize']}** (zastępując {reroll_target_user.mention}) to {new_winner.mention}!"
    else: # Normalne zakończenie lub ogólny reroll (jeśli nie podano kogo zastąpić)
        winner_count_to_draw = giveaway_data["winner_count"] if not reroll_target_user else num_to_reroll

        # Dla ogólnego reroll, losujemy spośród tych, co nie wygrali
        eligible_for_this_draw = [p for p in eligible_participants if p.id not in current_winners_ids] if current_winners_ids and not reroll_target_user else eligible_participants

        if eligible_for_this_draw:
            if len(eligible_for_this_draw) <= winner_count_to_draw:
                winners = eligible_for_this_draw
            else:
                winners = random.sample(eligible_for_this_draw, winner_count_to_draw)
            winner_ids = [w.id for w in winners]

        if not reroll_target_user: # Tylko przy pierwszym losowaniu lub pełnym rerollu nadpisujemy wszystkich
             database.end_giveaway(giveaway_data["id"], winner_ids)

        action_type_log_suffix = " (Manual Reroll)" if current_winners_ids and not reroll_target_user else ""
        results_title = f"🎉 Konkurs Zakończony{action_type_log_suffix}: {giveaway_data['prize']} 🎉"
        if winners:
            winner_mentions = [w.mention for w in winners]
            results_message_content = f"Gratulacje dla {', '.join(winner_mentions)}! Wygraliście **{giveaway_data['prize']}**!"
        elif not eligible_participants and participants_users:
            results_message_content = f"Niestety, nikt nie spełnił warunków konkursu na **{giveaway_data['prize']}**."
        else:
            results_message_content = f"Niestety, nikt nie wygrał w konkursie na **{giveaway_data['prize']}**."

    print(f"[GIVEAWAY_LOGIC] Konkurs ID {giveaway_data['id']}{action_type_log_suffix}. Zwycięzcy: {winner_ids}")

    results_embed = discord.Embed(title=results_title, color=discord.Color.dark_green() if winners else discord.Color.dark_red(), timestamp=datetime.utcnow())
    results_embed.add_field(name="Nagroda", value=giveaway_data['prize'], inline=False)
    if winners:
        results_embed.add_field(name=f"🏆 Zwycięzcy ({len(winners)}):", value=", ".join(w.mention for w in winners), inline=False)
    elif not eligible_participants and participants_users:
        results_embed.add_field(name="Wynik", value="Nikt z uczestników nie spełnił warunków.", inline=False)
    else:
        results_embed.add_field(name="Wynik", value="Brak kwalifikujących się uczestników.", inline=False)

    creator_id = giveaway_data['created_by_id']
    creator = guild.get_member(creator_id) or await bot.fetch_user(creator_id)
    if creator:
        results_embed.set_footer(text=f"Konkurs ID: {giveaway_data['id']} | Stworzony przez: {creator.display_name}")

    results_msg_obj = None
    try:
        results_msg_obj = await channel.send(content=results_message_content, embed=results_embed)
        if not reroll_target_user: # Tylko przy pierwszym zakończeniu edytuj oryginalną wiadomość
            try:
                original_embed = giveaway_message.embeds[0] if giveaway_message.embeds else None
                if original_embed:
                    new_embed_data = original_embed.to_dict()
                    new_embed_data['title'] = f"[ZAKOŃCZONY] {original_embed.title}"
                    new_embed_data['color'] = discord.Color.dark_grey().value
                    if 'fields' in new_embed_data:
                        new_embed_data['fields'] = [f for f in new_embed_data['fields'] if f['name'] not in ["Koniec", "Warunki udziału"]]
                    new_embed_data.setdefault('fields', []).append({'name': "Zwycięzcy", 'value': f"[Zobacz ogłoszenie]({results_msg_obj.jump_url})", 'inline': False})
                    final_original_embed = discord.Embed.from_dict(new_embed_data)
                    await giveaway_message.edit(embed=final_original_embed, view=None)
            except Exception as e_edit:
                print(f"[GIVEAWAY_LOGIC] Nie udało się edytować wiadomości konkursu {giveaway_data['message_id']}: {e_edit}")
    except Exception as e_send_results:
        print(f"[GIVEAWAY_LOGIC] Błąd wysyłania wyników konkursu {giveaway_data['id']}: {e_send_results}")
        return None, "Błąd podczas ogłaszania wyników."

    for winner_member in winners:
        try:
            await winner_member.send(f"🎉 Gratulacje! Wygrałeś/aś **{giveaway_data['prize']}** w konkursie na serwerze **{guild.name}**! Skontaktuj się z administracją.")
        except: pass # Ignoruj błędy DM

    return results_msg_obj, None


@tasks.loop(minutes=1)
async def check_ended_giveaways_task():
    await bot.wait_until_ready()
    current_timestamp = int(time.time())
    giveaways_to_end = database.get_active_giveaways_to_end(current_timestamp)

    if giveaways_to_end:
        print(f"[GIVEAWAY_TASK] Znaleziono {len(giveaways_to_end)} konkursów do zakończenia.")

    for giveaway_data in giveaways_to_end:
        guild = bot.get_guild(giveaway_data["guild_id"])
        if not guild:
            print(f"[GIVEAWAY_TASK] Nie znaleziono serwera {giveaway_data['guild_id']} dla konkursu ID {giveaway_data['id']}. Kończę w bazie.")
            database.end_giveaway(giveaway_data["id"], [])
            continue

        channel = guild.get_channel(giveaway_data["channel_id"])
        if not channel or not isinstance(channel, discord.TextChannel): # Upewnij się, że kanał jest tekstowy
            print(f"[GIVEAWAY_TASK] Nie znaleziono kanału {giveaway_data['channel_id']} dla konkursu ID {giveaway_data['id']}. Kończę w bazie.")
            database.end_giveaway(giveaway_data["id"], [])
            continue

        giveaway_message = None
        try:
            giveaway_message = await channel.fetch_message(giveaway_data["message_id"])
        except Exception as e: # NotFound lub inny błąd
            print(f"[GIVEAWAY_TASK] Błąd pobierania wiadomości dla konkursu {giveaway_data['id']}: {e}. Kończę w bazie.")
            database.end_giveaway(giveaway_data["id"], [])
            continue

        await _handle_giveaway_end_logic(guild, giveaway_data, giveaway_message)


@bot.tree.command(name="end_giveaway", description="Manualnie kończy konkurs i losuje zwycięzców.")
@app_commands.describe(id_wiadomosci_konkursu="ID wiadomości konkursu do zakończenia.")
@app_commands.checks.has_permissions(manage_guild=True)
async def end_giveaway_command(interaction: discord.Interaction, id_wiadomosci_konkursu: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        message_id = int(id_wiadomosci_konkursu)
    except ValueError:
        await interaction.followup.send("ID wiadomości musi być liczbą.", ephemeral=True)
        return

    giveaway_data = database.get_giveaway_details(message_id)
    if not giveaway_data:
        await interaction.followup.send(f"Nie znaleziono konkursu dla wiadomości o ID: {message_id}.", ephemeral=True)
        return
    if not giveaway_data["is_active"]:
        await interaction.followup.send(f"Ten konkurs (ID: {giveaway_data['id']}) jest już zakończony.", ephemeral=True)
        return

    giveaway_message = None
    try:
        channel = interaction.guild.get_channel(giveaway_data["channel_id"])
        if channel and isinstance(channel, discord.TextChannel): # Upewnij się, że kanał jest tekstowy
             giveaway_message = await channel.fetch_message(giveaway_data["message_id"])
    except Exception as e:
        print(f"Błąd pobierania wiadomości dla /end_giveaway {message_id}: {e}")

    if not giveaway_message:
        database.end_giveaway(giveaway_data["id"], [])
        await interaction.followup.send("Nie znaleziono oryginalnej wiadomości konkursu. Konkurs został zakończony w bazie bez losowania.", ephemeral=True)
        return

    _, error_message = await _handle_giveaway_end_logic(interaction.guild, giveaway_data, giveaway_message, is_manual_end=True)
    if error_message:
        await interaction.followup.send(error_message, ephemeral=True)
    else:
        await interaction.followup.send(f"Konkurs \"{giveaway_data['prize']}\" (ID: {giveaway_data['id']}) został manualnie zakończony i wyniki ogłoszone.", ephemeral=True)


@bot.tree.command(name="reroll_giveaway", description="Ponownie losuje zwycięzcę/ów dla zakończonego konkursu.")
@app_commands.describe(id_wiadomosci_konkursu="ID wiadomości zakończonego konkursu.",
                       uzytkownik_do_zastapienia="(Opcjonalnie) Zwycięzca, który ma zostać zastąpiony nowym losowaniem.",
                       liczba_nowych_zwyciezcow="(Opcjonalnie, jeśli nie zastępujesz) Ilu nowych zwycięzców wylosować dodatkowo lub zamiast wszystkich.")
@app_commands.checks.has_permissions(manage_guild=True)
async def reroll_giveaway_command(interaction: discord.Interaction, id_wiadomosci_konkursu: str,
                                  uzytkownik_do_zastapienia: discord.Member = None,
                                  liczba_nowych_zwyciezcow: int = None):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        message_id = int(id_wiadomosci_konkursu)
    except ValueError:
        await interaction.followup.send("ID wiadomości musi być liczbą.", ephemeral=True)
        return

    giveaway_data = database.get_giveaway_details(message_id)
    if not giveaway_data:
        await interaction.followup.send(f"Nie znaleziono konkursu dla wiadomości o ID: {message_id}.", ephemeral=True)
        return
    if giveaway_data["is_active"]:
        await interaction.followup.send(f"Konkurs (ID: {giveaway_data['id']}) musi być najpierw zakończony.", ephemeral=True)
        return

    giveaway_message = None
    try:
        channel = interaction.guild.get_channel(giveaway_data["channel_id"])
        if channel and isinstance(channel, discord.TextChannel): # Upewnij się, że kanał jest tekstowy
            giveaway_message = await channel.fetch_message(giveaway_data["message_id"])
    except Exception as e:
        print(f"Błąd pobierania wiadomości dla /reroll_giveaway {message_id}: {e}")

    if not giveaway_message:
        await interaction.followup.send("Nie znaleziono oryginalnej wiadomości konkursu. Reroll niemożliwy.", ephemeral=True)
        return

    num_to_reroll_val = liczba_nowych_zwyciezcow if liczba_nowych_zwyciezcow is not None else (1 if uzytkownik_do_zastapienia else giveaway_data["winner_count"])
    if num_to_reroll_val < 1 : num_to_reroll_val = 1


    _, error_message = await _handle_giveaway_end_logic(
        interaction.guild, giveaway_data, giveaway_message,
        reroll_target_user=uzytkownik_do_zastapienia,
        num_to_reroll=num_to_reroll_val
    )
    if error_message:
        await interaction.followup.send(error_message, ephemeral=True)
    else:
        await interaction.followup.send(f"Przeprowadzono ponowne losowanie dla konkursu \"{giveaway_data['prize']}\" (ID: {giveaway_data['id']}).", ephemeral=True)


# --- Moduł Ankiet ---
REGIONAL_INDICATOR_EMOJIS = [
    "🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯",
    "🇰", "🇱", "🇲", "🇳", "🇴", "🇵", "🇶", "🇷", "🇸", "🇹" # Max 20 opcji na razie
]

@bot.tree.command(name="create_poll", description="Tworzy nową ankietę z opcjami do głosowania przez reakcje.")
@app_commands.describe(
    pytanie="Pytanie ankiety.",
    opcje="Opcje odpowiedzi, rozdzielone znakiem '|' (np. Opcja A|Opcja B|Opcja C). Maksymalnie 20 opcji.",
    czas_trwania="Czas trwania ankiety (np. 30m, 2h, 1d). Domyślnie 24h. Wpisz '0s' dla ankiety bez limitu czasu.",
    kanal="Na którym kanale opublikować ankietę (domyślnie aktualny kanał)."
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_poll_command(interaction: discord.Interaction,
                              pytanie: str,
                              opcje: str,
                              czas_trwania: str = "24h",
                              kanal: discord.TextChannel = None):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    target_channel = kanal if kanal else interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("Ankieta może być opublikowana tylko na kanale tekstowym.", ephemeral=True)
        return

    parsed_options = [opt.strip() for opt in opcje.split('|') if opt.strip()]
    if not parsed_options or len(parsed_options) < 2:
        await interaction.response.send_message("Musisz podać przynajmniej dwie opcje odpowiedzi, rozdzielone znakiem '|'.", ephemeral=True)
        return
    if len(parsed_options) > len(REGIONAL_INDICATOR_EMOJIS):
        await interaction.response.send_message(f"Możesz podać maksymalnie {len(REGIONAL_INDICATOR_EMOJIS)} opcji odpowiedzi.", ephemeral=True)
        return

    ends_at_timestamp = None
    if czas_trwania and czas_trwania.lower() not in ['0', '0s', 'none', 'permanent']:
        duration_seconds = time_parser.parse_duration(czas_trwania)
        if duration_seconds is None or duration_seconds < 0:
            await interaction.response.send_message("Nieprawidłowy format czasu trwania. Użyj np. 30m, 2h, 1d lub '0s' dla braku limitu.", ephemeral=True)
            return
        if duration_seconds > 0 :
             ends_at_timestamp = int(time.time() + duration_seconds)

    try:
        poll_id = database.create_poll(
            guild_id=interaction.guild_id,
            channel_id=target_channel.id,
            question=pytanie,
            created_by_id=interaction.user.id,
            ends_at=ends_at_timestamp
        )
        if poll_id is None:
            await interaction.response.send_message("Nie udało się utworzyć ankiety w bazie danych.", ephemeral=True)
            return

        poll_options_with_emoji = []
        for i, option_text in enumerate(parsed_options):
            emoji = REGIONAL_INDICATOR_EMOJIS[i]
            database.add_poll_option(poll_id, option_text, emoji)
            poll_options_with_emoji.append(f"{emoji} {option_text}")

        embed = discord.Embed(
            title=f"📊 Ankieta: {pytanie}",
            description="\n\n".join(poll_options_with_emoji),
            color=discord.Color.blurple(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Ankieta stworzona przez {interaction.user.display_name} | ID Ankiety: {poll_id}")
        if ends_at_timestamp:
            embed.add_field(name="Koniec głosowania", value=f"<t:{ends_at_timestamp}:F> (<t:{ends_at_timestamp}:R>)")
        else:
            embed.add_field(name="Koniec głosowania", value="Nigdy (ręczne zamknięcie)")

        poll_message = await target_channel.send(embed=embed)
        database.set_poll_message_id(poll_id, poll_message.id)

        for i in range(len(parsed_options)):
            await poll_message.add_reaction(REGIONAL_INDICATOR_EMOJIS[i])

        await interaction.response.send_message(f"Ankieta została pomyślnie utworzona na kanale {target_channel.mention}!", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message(f"Nie mam uprawnień do wysłania wiadomości lub dodania reakcji na kanale {target_channel.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił nieoczekiwany błąd podczas tworzenia ankiety: {e}", ephemeral=True)
        print(f"Błąd w /create_poll: {e}")

@create_poll_command.error
async def create_poll_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień do zarządzania serwerem, aby utworzyć ankietę.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"Wystąpił błąd: {error}", ephemeral=True)
        print(f"Błąd w create_poll_error: {error}")

# --- Zadanie w Tle do Zamykania Ankiet ---
@tasks.loop(minutes=1)
async def check_expired_polls_task():
    await bot.wait_until_ready()
    current_timestamp = int(time.time())
    polls_to_close = database.get_active_polls_to_close(current_timestamp)

    if polls_to_close:
        print(f"[POLL_TASK] Znaleziono {len(polls_to_close)} ankiet do zamknięcia.")

    for poll_data in polls_to_close:
        guild = bot.get_guild(poll_data["guild_id"])
        if not guild:
            print(f"[POLL_TASK] Nie znaleziono serwera {poll_data['guild_id']} dla ankiety ID {poll_data['id']}. Zamykam w bazie.")
            database.close_poll(poll_data["id"])
            continue

        channel = guild.get_channel(poll_data["channel_id"])
        if not channel or not isinstance(channel, discord.TextChannel):
            print(f"[POLL_TASK] Nie znaleziono kanału {poll_data['channel_id']} dla ankiety ID {poll_data['id']} na serwerze {guild.name}. Zamykam w bazie.")
            database.close_poll(poll_data["id"])
            continue

        try:
            poll_message = await channel.fetch_message(poll_data["message_id"])
        except discord.NotFound:
            print(f"[POLL_TASK] Nie znaleziono wiadomości ankiety {poll_data['message_id']} dla ankiety ID {poll_data['id']}. Zamykam w bazie.")
            database.close_poll(poll_data["id"])
            continue
        except discord.Forbidden:
            print(f"[POLL_TASK] Brak uprawnień do pobrania wiadomości ankiety {poll_data['message_id']} (Ankieta ID {poll_data['id']}). Zamykam w bazie.")
            database.close_poll(poll_data["id"])
            continue
        except Exception as e:
            print(f"[POLL_TASK] Inny błąd przy pobieraniu wiadomości ankiety {poll_data['message_id']}: {e}. Zamykam w bazie.")
            database.close_poll(poll_data["id"])
            continue

        poll_options = database.get_poll_options(poll_data["id"])
        if not poll_options:
            print(f"[POLL_TASK] Brak opcji dla ankiety ID {poll_data['id']}. Zamykam w bazie.")
            database.close_poll(poll_data["id"])
            continue

        results = {} # emoji: count
        total_votes = 0
        for reaction in poll_message.reactions:
            emoji_str = str(reaction.emoji)
            is_option_emoji = any(opt['reaction_emoji'] == emoji_str for opt in poll_options)
            if is_option_emoji:
                users = [user async for user in reaction.users() if not user.bot]
                count = len(users)

                results[emoji_str] = count
                total_votes += count

        results_embed = discord.Embed(
            title=f"📊 Wyniki Ankiety: {poll_data['question']}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        results_description_parts = []
        sorted_options = sorted(poll_options, key=lambda x: results.get(x['reaction_emoji'], 0), reverse=True)

        for option in sorted_options:
            emoji = option['reaction_emoji']
            text = option['option_text']
            votes = results.get(emoji, 0)
            percentage = (votes / total_votes * 100) if total_votes > 0 else 0

            bar_length = 10
            filled_blocks = int(bar_length * (percentage / 100))
            bar = '█' * filled_blocks + '░' * (bar_length - filled_blocks)

            results_description_parts.append(
                f"{emoji} **{text}**: {votes} głosów ({percentage:.1f}%)\n`{bar}`"
            )

        if not results_description_parts:
            results_embed.description = "Nikt nie zagłosował w tej ankiecie."
        else:
            results_embed.description = "\n\n".join(results_description_parts)

        results_embed.add_field(name="Całkowita liczba głosów", value=str(total_votes))
        creator = guild.get_member(poll_data['created_by_id']) or await bot.fetch_user(poll_data['created_by_id'])
        if creator:
            results_embed.set_footer(text=f"Ankieta stworzona przez {creator.display_name} | ID Ankiety: {poll_data['id']}")

        results_message = None
        try:
            results_message = await channel.send(embed=results_embed)
            try:
                original_embed = poll_message.embeds[0] if poll_message.embeds else None
                if original_embed:
                    new_embed_data = original_embed.to_dict()
                    new_embed_data['title'] = "[ZAKOŃCZONA] " + new_embed_data.get('title', poll_data['question'])
                    new_embed_data['color'] = discord.Color.dark_grey().value
                    if 'fields' in new_embed_data:
                        new_embed_data['fields'] = [f for f in new_embed_data['fields'] if f['name'] != "Koniec głosowania"]
                    new_embed_data.setdefault('fields', []).append({'name': "Wyniki", 'value': f"[Zobacz wyniki]({results_message.jump_url})", 'inline': False})

                    final_embed = discord.Embed.from_dict(new_embed_data)
                    await poll_message.edit(embed=final_embed, view=None)
                    await poll_message.clear_reactions()
            except Exception as e_edit:
                print(f"[POLL_TASK] Nie udało się edytować oryginalnej wiadomości ankiety ID {poll_data['message_id']}: {e_edit}")

        except discord.Forbidden:
            print(f"[POLL_TASK] Brak uprawnień do wysłania wyników ankiety ID {poll_data['id']} na kanale {channel.name}.")
        except Exception as e_send_results:
            print(f"[POLL_TASK] Błąd wysyłania wyników ankiety ID {poll_data['id']}: {e_send_results}")

        database.close_poll(poll_data["id"], results_message_id=results_message.id if results_message else None)
        print(f"[POLL_TASK] Ankieta ID {poll_data['id']} została zamknięta i wyniki ogłoszone.")


@bot.tree.command(name="close_poll", description="Manualnie zamyka aktywną ankietę i ogłasza wyniki.")
@app_commands.describe(id_wiadomosci_ankiety="ID wiadomości, na której znajduje się ankieta do zamknięcia.")
@app_commands.checks.has_permissions(manage_guild=True)
async def close_poll_command(interaction: discord.Interaction, id_wiadomosci_ankiety: str):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    try:
        message_id = int(id_wiadomosci_ankiety)
    except ValueError:
        await interaction.response.send_message("ID wiadomości musi być liczbą.", ephemeral=True)
        return

    poll_data = database.get_poll_by_message_id(message_id)

    if not poll_data:
        await interaction.response.send_message(f"Nie znaleziono ankiety powiązanej z wiadomością o ID: {message_id}.", ephemeral=True)
        return

    if not poll_data["is_active"]:
        await interaction.response.send_message(f"Ankieta (ID: {poll_data['id']}) jest już zamknięta.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    guild = interaction.guild

    giveaway_message = None # Zmieniono nazwę zmiennej dla jasności
    try:
        channel = guild.get_channel(poll_data["channel_id"])
        if channel and isinstance(channel, discord.TextChannel):
             giveaway_message = await channel.fetch_message(poll_data["message_id"])
    except Exception as e:
        print(f"Błąd pobierania wiadomości dla /close_poll {message_id}: {e}")

    if not giveaway_message: # Jeśli nie udało się pobrać wiadomości ankiety
        database.close_poll(poll_data["id"])
        await interaction.followup.send("Nie znaleziono oryginalnej wiadomości ankiety. Ankieta została zamknięta w bazie bez ogłaszania wyników.", ephemeral=True)
        return

    # Użyj _handle_giveaway_end_logic - pomyłka, to powinno być dla ankiet
    # Trzeba zrefaktoryzować logikę kończenia ankiety do osobnej funkcji, tak jak dla konkursów.
    # Na razie skopiuję i dostosuję logikę z check_expired_polls_task.

    poll_options = database.get_poll_options(poll_data["id"])
    if not poll_options:
        print(f"[CLOSE_POLL] Brak opcji dla ankiety ID {poll_data['id']}. Zamykam w bazie.")
        database.close_poll(poll_data["id"])
        await interaction.followup.send(f"Brak opcji dla ankiety. Ankieta (ID: {poll_data['id']}) została zamknięta w bazie.", ephemeral=True)
        return

    results = {}
    total_votes = 0
    for reaction in giveaway_message.reactions: # giveaway_message to tak naprawdę poll_message
        emoji_str = str(reaction.emoji)
        is_option_emoji = any(opt['reaction_emoji'] == emoji_str for opt in poll_options)
        if is_option_emoji:
            users = [user async for user in reaction.users() if not user.bot]
            count = len(users)
            results[emoji_str] = count
            total_votes += count

    results_embed = discord.Embed(
        title=f"📊 Wyniki Ankiety (Zamknięta Manualnie): {poll_data['question']}",
        color=discord.Color.dark_red(),
        timestamp=datetime.utcnow()
    )
    results_description_parts = []
    sorted_options = sorted(poll_options, key=lambda x: results.get(x['reaction_emoji'], 0), reverse=True)

    for option in sorted_options:
        emoji = option['reaction_emoji']
        text = option['option_text']
        votes = results.get(emoji, 0)
        percentage = (votes / total_votes * 100) if total_votes > 0 else 0
        bar_length = 10
        filled_blocks = int(bar_length * (percentage / 100))
        bar = '█' * filled_blocks + '░' * (bar_length - filled_blocks)
        results_description_parts.append(f"{emoji} **{text}**: {votes} głosów ({percentage:.1f}%)\n`{bar}`")

    results_embed.description = "\n\n".join(results_description_parts) if results_description_parts else "Nikt nie zagłosował."
    results_embed.add_field(name="Całkowita liczba głosów", value=str(total_votes))
    creator = guild.get_member(poll_data['created_by_id']) or await bot.fetch_user(poll_data['created_by_id'])
    if creator:
        results_embed.set_footer(text=f"Ankieta ID: {poll_data['id']} | Zamknięta przez: {interaction.user.display_name}")

    results_message_obj = None
    try:
        results_message_obj = await giveaway_message.channel.send(embed=results_embed) # Użyj giveaway_message.channel
        try:
            original_embed = giveaway_message.embeds[0] if giveaway_message.embeds else None
            if original_embed:
                new_embed_data = original_embed.to_dict()
                new_embed_data['title'] = "[ZAMKNIĘTA MANUALNIE] " + new_embed_data.get('title', poll_data['question'])
                new_embed_data['color'] = discord.Color.dark_grey().value
                if 'fields' in new_embed_data:
                    new_embed_data['fields'] = [f for f in new_embed_data['fields'] if f['name'] != "Koniec głosowania"]
                new_embed_data.setdefault('fields', []).append({'name': "Wyniki", 'value': f"[Zobacz wyniki]({results_message_obj.jump_url})", 'inline': False})
                final_embed = discord.Embed.from_dict(new_embed_data)
                await giveaway_message.edit(embed=final_embed, view=None)
                await giveaway_message.clear_reactions()
        except Exception as e_edit:
            print(f"[CLOSE_POLL] Nie udało się edytować oryginalnej wiadomości ankiety ID {poll_data['message_id']}: {e_edit}")

        database.close_poll(poll_data["id"], results_message_id=results_message_obj.id if results_message_obj else None)
        await interaction.followup.send(f"Ankieta (ID: {poll_data['id']}) została zamknięta. Wyniki ogłoszone.", ephemeral=True)
    except Exception as e_send_results:
        print(f"[CLOSE_POLL] Błąd wysyłania wyników ankiety ID {poll_data['id']}: {e_send_results}")
        database.close_poll(poll_data["id"])
        await interaction.followup.send(f"Wystąpił błąd podczas ogłaszania wyników, ale ankieta (ID: {poll_data['id']}) została zamknięta w bazie.", ephemeral=True)


@close_poll_command.error
async def close_poll_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień do zarządzania serwerem, aby zamknąć ankietę.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"Wystąpił błąd: {error}", ephemeral=True)
        print(f"Błąd w close_poll_error: {error}")

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
        return # Zakończ przetwarzanie dla odpowiedzi na quiz

    # 2. Ignoruj boty i wiadomości prywatne (jeśli nie były odpowiedzią na quiz) dla dalszych akcji
    if message.author.bot or not message.guild:
        return

    # 3. Logika Moderacji (jeśli wiadomość z serwera i nie od bota)
    message_deleted_by_moderation = False
    server_config_mod = database.get_server_config(message.guild.id)
    if server_config_mod:
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
        return

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

    # 5. Obsługa komend tekstowych (jeśli są)
    # await bot.process_commands(message)

bot.on_message = on_message # Zmieniono nazwę handlera i sposób rejestracji


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
    progress_bar = "█" * 10 + " (MAX POZIOM)" # Domyślnie, jeśli nie ma następnego poziomu
    progress_percentage = 100.0

    if xp_needed_for_level_up_from_current > 0 : # Normalny postęp
        progress_percentage = (xp_in_current_level / xp_needed_for_level_up_from_current) * 100
        filled_blocks = int(progress_percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "█" * filled_blocks + "░" * empty_blocks
        xp_display = f"{xp_in_current_level:,} / {xp_needed_for_level_up_from_current:,} XP na tym poziomie (Całkowite: {current_xp:,})"
    elif current_level == 0 and xp_for_next_level_gate > 0 : # Poziom 0, postęp do poziomu 1
        progress_percentage = (current_xp / xp_for_next_level_gate) * 100
        filled_blocks = int(progress_percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "█" * filled_blocks + "░" * empty_blocks
        xp_display = f"{current_xp:,} / {xp_for_next_level_gate:,} XP (Całkowite: {current_xp:,})"
    else: # Brak zdefiniowanego następnego poziomu (lub błąd w formule dla level 0)
        xp_display = f"Całkowite XP: {current_xp:,}"


    embed = discord.Embed(title=f"Statystyki Aktywności dla {target_user.display_name}", color=discord.Color.green() if target_user == interaction.user else discord.Color.blue())
    embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="Poziom", value=f"**{current_level}**", inline=True)
    embed.add_field(name="Całkowite XP", value=f"**{current_xp:,}**", inline=True) # Dodane formatowanie z przecinkami

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
            f"**{rank_pos}.** {user_display_name} - Poziom: **{entry['level']}** (XP: {entry['xp']:,})" # Formatowanie XP
        )

    embed.description = "\n".join(description_lines)

    # Sprawdzenie, czy jest następna strona
    # Aby to zrobić poprawnie, potrzebujemy znać całkowitą liczbę użytkowników w rankingu.
    # Możemy to uzyskać np. przez `get_user_rank_in_server` dla dowolnego użytkownika z XP lub osobną funkcję.
    # Na razie uproszczenie: jeśli pobraliśmy pełną stronę (limit_per_page), jest szansa na następną.
    if len(leaderboard_data) == limit_per_page:
        # Sprawdź, czy istnieje przynajmniej jeden kolejny użytkownik
        next_page_check = database.get_server_leaderboard(interaction.guild_id, limit=1, offset=strona * limit_per_page)
        if next_page_check:
             embed.add_field(name="\u200b", value=f"Użyj `/leaderboard strona:{strona + 1}` aby zobaczyć następną stronę.", inline=False)

    await interaction.response.send_message(embed=embed)


# --- System Weryfikacji Quizem ---
# ... (reszta kodu bez zmian)
[end of main.py]
