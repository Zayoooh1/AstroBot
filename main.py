import discord
from discord import app_commands # Import dla komend aplikacyjnych
from discord.ext import commands # Możemy użyć Bot zamiast Client dla lepszej obsługi komend
import os
from dotenv import load_dotenv
import database # Import naszego modułu bazy danych
import leveling # Import modułu systemu poziomowania
import random # Do losowania XP
import time # Do cooldownu XP i timestampów

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

# Definiujemy intencje, w tym guilds i members, które mogą być potrzebne
intents = discord.Intents.default()
intents.message_content = True # Jeśli nadal potrzebne dla starych komend tekstowych lub innych funkcji
intents.guilds = True
intents.members = True # Potrzebne do nadawania ról

# Używamy Bot zamiast Client dla łatwiejszej obsługi komend aplikacyjnych
bot = commands.Bot(command_prefix="!", intents=intents) # Prefix może być dowolny, jeśli nie używamy już komend tekstowych

@bot.event
async def on_ready():
    print(f'Zalogowano jako {bot.user}')
    try:
        # Inicjalizacja bazy danych przy starcie bota
        database.init_db()
        print("Baza danych zainicjalizowana.")
        # Synchronizacja komend aplikacyjnych
        # Dla testowania można synchronizować tylko z jednym serwerem, aby było szybciej
        # GUILD_ID = discord.Object(id=YOUR_TEST_SERVER_ID) # Zastąp YOUR_TEST_SERVER_ID
        # bot.tree.copy_global_to(guild=GUILD_ID)
        # synced = await bot.tree.sync(guild=GUILD_ID)
        # Dla globalnej synchronizacji:
        synced = await bot.tree.sync()
        print(f"Zsynchronizowano {len(synced)} komend(y).")
    except Exception as e:
        print(f"Wystąpił błąd podczas synchronizacji komend: {e}")

# Komenda do ustawiania wiadomości powitalnej
@bot.tree.command(name="set_welcome_message", description="Ustawia treść wiadomości powitalnej dla reakcji.")
@app_commands.describe(tresc="Treść wiadomości powitalnej")
@app_commands.checks.has_permissions(administrator=True) # Tylko administratorzy mogą użyć tej komendy
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
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    try:
        # Sprawdzenie, czy bot może zarządzać tą rolą (czy rola bota jest wyżej i ma uprawnienia)
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

# Komenda do wysłania wiadomości weryfikacyjnej
REACTION_EMOJI = "✅"

@bot.tree.command(name="verify", description="Wysyła wiadomość weryfikacyjną, na którą użytkownicy mogą reagować.")
@app_commands.checks.has_permissions(administrator=True)
async def verify_command(interaction: discord.Interaction):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    config = database.get_server_config(interaction.guild_id)

    if not config or not config.get("welcome_message_content") or not config.get("reaction_role_id"):
        await interaction.response.send_message(
            "Konfiguracja dla tego serwera jest niekompletna. "
            "Użyj `/set_welcome_message` i `/set_verification_role`, aby ją ustawić.",
            ephemeral=True
        )
        return

    welcome_message_content = config["welcome_message_content"]
    reaction_role_id = config["reaction_role_id"]

    role_to_assign = interaction.guild.get_role(reaction_role_id)
    if not role_to_assign:
        await interaction.response.send_message(
            f"Skonfigurowana rola (ID: {reaction_role_id}) nie została znaleziona na tym serwerze. "
            "Sprawdź konfigurację za pomocą `/set_verification_role`.",
            ephemeral=True
        )
        return

    try:
        # Upewniamy się, że interaction.channel nie jest None i ma metodę send
        if interaction.channel is None:
            await interaction.response.send_message("Nie udało się wysłać wiadomości na tym kanale.", ephemeral=True)
            return

        # Wysyłamy wiadomość na kanale, na którym użyto komendy
        # Używamy `await interaction.response.defer(ephemeral=False)` aby móc wysłać wiadomość, która nie jest efemeryczna
        # a następnie `interaction.followup.send()` lub `interaction.channel.send()`
        # Jednakże, jeśli chcemy po prostu wysłać nową wiadomość na kanale, a komenda sama w sobie może być efemeryczna (potwierdzenie)
        # to lepiej zrobić to tak:

        # Najpierw odpowiadamy na interakcję (np. efemerycznie, że zadanie wykonano)
        await interaction.response.send_message("Przygotowuję wiadomość weryfikacyjną...", ephemeral=True)

        # A potem wysyłamy właściwą wiadomość na kanale
        # Sprawdzamy czy kanał jest TextChannel, aby uniknąć problemów z typami
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send("Nie można wysłać wiadomości na tym typie kanału.", ephemeral=True)
            return

        reaction_message = await interaction.channel.send(content=welcome_message_content)
        await reaction_message.add_reaction(REACTION_EMOJI)

        # Zapisz ID wiadomości w bazie danych
        database.update_server_config(guild_id=interaction.guild_id, reaction_message_id=reaction_message.id)

        # Potwierdzenie dla admina (może być w followup, jeśli pierwotna odpowiedź była defer)
        await interaction.followup.send(f"Wiadomość weryfikacyjna została wysłana na kanale {interaction.channel.mention}. ID wiadomości: {reaction_message.id}", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send( # Używamy followup, bo już odpowiedzieliśmy na interakcję
            "Nie mam uprawnień do wysłania wiadomości, dodania reakcji na tym kanale lub zarządzania rolami. "
            "Sprawdź moje uprawnienia.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"Wystąpił błąd podczas wysyłania wiadomości weryfikacyjnej: {e}", ephemeral=True)

@verify_command.error
async def verify_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień do użycia tej komendy.", ephemeral=True)
    else:
        # Jeśli odpowiedź na interakcję nie została jeszcze wysłana
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Wystąpił nieoczekiwany błąd: {error}", ephemeral=True)
        else: # Jeśli już odpowiedziano, użyj followup
            await interaction.followup.send(f"Wystąpił nieoczekiwany błąd: {error}", ephemeral=True)

# Event handler dla dodania reakcji
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.member is None or payload.member.bot: # Ignoruj reakcje od botów (w tym samego siebie)
        return

    if str(payload.emoji) == REACTION_EMOJI: # Sprawdź, czy to nasza docelowa emoji
        config = database.get_server_config(payload.guild_id)

        if config and config.get("reaction_message_id") == payload.message_id and config.get("reaction_role_id"):
            guild = bot.get_guild(payload.guild_id)
            if not guild:
                print(f"Błąd: Nie znaleziono serwera o ID {payload.guild_id}")
                return

            role_id = config.get("reaction_role_id")
            role_to_assign = guild.get_role(role_id)

            if not role_to_assign:
                print(f"Błąd: Rola o ID {role_id} nie została znaleziona na serwerze {guild.name}")
                # Można dodać powiadomienie dla admina serwera, jeśli rola zniknęła
                return

            member = payload.member # payload.member jest już obiektem discord.Member dzięki intencjom
            if member: # Upewnij się, że member nie jest None
                try:
                    # Sprawdzenie hierarchii ról i uprawnień bota
                    if guild.me.top_role <= role_to_assign:
                        print(f"Ostrzeżenie: Bot nie może nadać roli {role_to_assign.name} na serwerze {guild.name}, ponieważ rola bota nie jest wystarczająco wysoko.")
                        # Można wysłać wiadomość do użytkownika lub admina
                        return

                    if not guild.me.guild_permissions.manage_roles:
                        print(f"Ostrzeżenie: Bot nie ma uprawnień do zarządzania rolami na serwerze {guild.name}.")
                        return

                    if role_to_assign not in member.roles: # Nadaj rolę tylko jeśli użytkownik jej jeszcze nie ma
                        await member.add_roles(role_to_assign, reason="Reakcja na wiadomość weryfikacyjną")
                        print(f"Nadano rolę {role_to_assign.name} użytkownikowi {member.name} na serwerze {guild.name}")
                        try:
                            await member.send(f"Otrzymałeś/aś rolę **{role_to_assign.name}** na serwerze **{guild.name}**.")
                        except discord.Forbidden:
                            print(f"Nie udało się wysłać PW do {member.name} - zablokowane PW lub brak wspólnego serwera (co nie powinno tu mieć miejsca).")
                except discord.Forbidden:
                    print(f"Błąd uprawnień: Nie udało się nadać roli {role_to_assign.name} użytkownikowi {member.name} na serwerze {guild.name}. Sprawdź uprawnienia bota i hierarchię ról.")
                except Exception as e:
                    print(f"Nieoczekiwany błąd podczas nadawania roli: {e}")
            else:
                print(f"Błąd: Nie udało się pobrać obiektu Member dla użytkownika o ID {payload.user_id}")

# Event handler dla usunięcia reakcji
@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    # Nie ignorujemy botów tutaj, bo użytkownik może usunąć reakcję bota (chociaż nie powinno to mieć wpływu na role użytkowników)
    # Ale najważniejsze to user_id, które nie będzie botem, jeśli to użytkownik usuwa swoją reakcję.

    # Potrzebujemy pobrać obiekt guild, aby dostać membera, bo payload.member nie jest dostępne w on_raw_reaction_remove
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        print(f"Błąd (on_raw_reaction_remove): Nie znaleziono serwera o ID {payload.guild_id}")
        return

    member = guild.get_member(payload.user_id)
    if not member or member.bot: # Ignoruj, jeśli użytkownik nie znaleziony lub to bot
        return

    if str(payload.emoji) == REACTION_EMOJI:
        config = database.get_server_config(payload.guild_id)

        if config and config.get("reaction_message_id") == payload.message_id and config.get("reaction_role_id"):
            role_id = config.get("reaction_role_id")
            role_to_remove = guild.get_role(role_id)

            if not role_to_remove:
                print(f"Błąd (on_raw_reaction_remove): Rola o ID {role_id} nie została znaleziona na serwerze {guild.name}")
                return

            try:
                # Sprawdzenie hierarchii ról i uprawnień bota (tak jak przy dodawaniu)
                if guild.me.top_role <= role_to_remove:
                    print(f"Ostrzeżenie (on_raw_reaction_remove): Bot nie może odebrać roli {role_to_remove.name} na serwerze {guild.name}, rola bota nie jest wystarczająco wysoko.")
                    return

                if not guild.me.guild_permissions.manage_roles:
                    print(f"Ostrzeżenie (on_raw_reaction_remove): Bot nie ma uprawnień do zarządzania rolami na serwerze {guild.name}.")
                    return

                if role_to_remove in member.roles: # Odbierz rolę tylko jeśli użytkownik ją posiada
                    await member.remove_roles(role_to_remove, reason="Usunięcie reakcji z wiadomości weryfikacyjnej")
                    print(f"Odebrano rolę {role_to_remove.name} użytkownikowi {member.name} na serwerze {guild.name}")
                    try:
                        await member.send(f"Twoja rola **{role_to_remove.name}** na serwerze **{guild.name}** została usunięta, ponieważ usunąłeś/aś reakcję.")
                    except discord.Forbidden:
                        print(f"Nie udało się wysłać PW do {member.name} o usunięciu roli.")
            except discord.Forbidden:
                print(f"Błąd uprawnień (on_raw_reaction_remove): Nie udało się odebrać roli {role_to_remove.name} użytkownikowi {member.name} na serwerze {guild.name}.")
            except Exception as e:
                print(f"Nieoczekiwany błąd podczas odbierania roli: {e}")


if TOKEN:
    bot.run(TOKEN)
else:
    print("Błąd: Nie znaleziono tokena bota w pliku .env")

# --- Role Czasowe ---
import time # Potrzebne do pracy z timestampami

@bot.tree.command(name="temprole", description="Nadaje użytkownikowi rolę na określony czas.")
@app_commands.describe(uzytkownik="Użytkownik, któremu nadać rolę",
                       rola="Rola do nadania",
                       czas="Czas trwania roli (liczba)",
                       jednostka="Jednostka czasu (minuty, godziny, dni)")
@app_commands.choices(jednostka=[
    app_commands.Choice(name="Minuty", value="minuty"),
    app_commands.Choice(name="Godziny", value="godziny"),
    app_commands.Choice(name="Dni", value="dni"),
])
@app_commands.checks.has_permissions(manage_roles=True)
async def temprole_command(interaction: discord.Interaction,
                           uzytkownik: discord.Member,
                           rola: discord.Role,
                           czas: int,
                           jednostka: app_commands.Choice[str] = None): # Jednostka domyślnie None, obsłużymy to

    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    # Ustawienie domyślnej jednostki na minuty, jeśli nie podano
    actual_jednostka = jednostka.value if jednostka else "minuty"

    if czas <= 0:
        await interaction.response.send_message("Czas trwania roli musi być liczbą dodatnią.", ephemeral=True)
        return

    # Konwersja czasu na sekundy
    duration_seconds = 0
    if actual_jednostka == "minuty":
        duration_seconds = czas * 60
    elif actual_jednostka == "godziny":
        duration_seconds = czas * 60 * 60
    elif actual_jednostka == "dni":
        duration_seconds = czas * 60 * 60 * 24
    else: # Powinno być obsłużone przez choices, ale dla pewności
        await interaction.response.send_message("Nieprawidłowa jednostka czasu.", ephemeral=True)
        return

    # Sprawdzenie, czy bot może zarządzać tą rolą
    if interaction.guild.me.top_role <= rola:
        await interaction.response.send_message(
            f"Nie mogę nadać roli {rola.mention}, ponieważ jest ona na tym samym lub wyższym poziomie w hierarchii niż moja najwyższa rola.",
            ephemeral=True
        )
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "Nie mam uprawnień do zarządzania rolami na tym serwerze.",
            ephemeral=True
        )
        return

    # Sprawdzenie, czy użytkownik ma już tę rolę czasową aktywną
    active_role_info = database.get_active_timed_role(interaction.guild_id, uzytkownik.id, rola.id)
    if active_role_info:
        # Możemy zdecydować, czy przedłużyć, czy poinformować o aktywnej roli. Na razie informujemy.
        current_expiration = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(active_role_info['expiration_timestamp']))
        await interaction.response.send_message(
            f"{uzytkownik.mention} ma już aktywną rolę {rola.mention}, która wygasa {current_expiration}. "
            "Jeśli chcesz zmienić czas, usuń najpierw starą rolę (funkcjonalność do dodania) lub poczekaj na jej wygaśnięcie.",
            ephemeral=True
        )
        return

    expiration_timestamp = int(time.time() + duration_seconds)

    try:
        await uzytkownik.add_roles(rola, reason=f"Nadano czasowo przez {interaction.user.name} na {czas} {actual_jednostka}")
        database.add_timed_role(interaction.guild_id, uzytkownik.id, rola.id, expiration_timestamp)

        expiration_readable = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(expiration_timestamp))
        await interaction.response.send_message(
            f"Nadano rolę {rola.mention} użytkownikowi {uzytkownik.mention} na {czas} {actual_jednostka}. "
            f"Rola wygaśnie {expiration_readable}.",
            ephemeral=False # Można zmienić na True, jeśli chcemy tylko dla admina
        )
        try:
            await uzytkownik.send(
                f"Otrzymałeś/aś czasową rolę **{rola.name}** na serwerze **{interaction.guild.name}** na okres {czas} {actual_jednostka}. "
                f"Rola wygaśnie {expiration_readable}."
            )
        except discord.Forbidden:
            print(f"Nie udało się wysłać PW do {uzytkownik.name} o nadaniu roli czasowej.")

    except discord.Forbidden:
        await interaction.response.send_message("Wystąpił błąd uprawnień podczas próby nadania roli.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił nieoczekiwany błąd: {e}", ephemeral=True)
        print(f"Błąd w /temprole: {e}")


@temprole_command.error
async def temprole_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień do zarządzania rolami, aby użyć tej komendy.", ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, discord.Forbidden):
        await interaction.response.send_message(
            "Wystąpił błąd uprawnień. Upewnij się, że rola bota jest wyżej w hierarchii niż nadawana rola "
            "oraz że bot ma uprawnienie 'Zarządzanie rolami'.",
            ephemeral=True
        )
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Wystąpił nieoczekiwany błąd w komendzie temprole: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"Wystąpił nieoczekiwany błąd w komendzie temprole: {error}", ephemeral=True)
        print(f"Błąd w temprole_command_error: {error}")

# Zadanie w tle do obsługi wygasania ról czasowych
from discord.ext import tasks

@tasks.loop(seconds=60) # Uruchamiaj co 60 sekund
async def check_expired_roles():
    await bot.wait_until_ready() # Poczekaj, aż bot będzie gotowy

    current_timestamp = int(time.time())
    expired_entries = database.get_expired_roles(current_timestamp)

    if expired_entries:
        print(f"Znaleziono {len(expired_entries)} wygasłych ról czasowych do przetworzenia.")

    for entry in expired_entries:
        entry_id, guild_id, user_id, role_id, expiration_ts = entry

        guild = bot.get_guild(guild_id)
        if not guild:
            print(f"Nie znaleziono serwera o ID {guild_id} dla wpisu {entry_id}. Usuwam wpis.")
            database.remove_timed_role(entry_id)
            continue

        role = guild.get_role(role_id)
        if not role:
            print(f"Nie znaleziono roli o ID {role_id} na serwerze {guild.name} dla wpisu {entry_id}. Usuwam wpis.")
            database.remove_timed_role(entry_id)
            continue

        member = guild.get_member(user_id)
        if not member:
            print(f"Nie znaleziono użytkownika o ID {user_id} na serwerze {guild.name} dla wpisu {entry_id}. Usuwam wpis.")
            # Użytkownik mógł opuścić serwer, więc rola i tak nie istnieje na nim.
            database.remove_timed_role(entry_id)
            continue

        # Sprawdzenie hierarchii i uprawnień przed próbą usunięcia roli
        if guild.me.top_role <= role:
            print(f"Ostrzeżenie (check_expired_roles): Bot nie może odebrać roli {role.name} użytkownikowi {member.name} na serwerze {guild.name}, rola bota nie jest wystarczająco wysoko. Wpis {entry_id} pozostaje na razie w bazie.")
            # Można dodać logikę ponawiania lub powiadamiania admina
            continue

        if not guild.me.guild_permissions.manage_roles:
            print(f"Ostrzeżenie (check_expired_roles): Bot nie ma uprawnień do zarządzania rolami na serwerze {guild.name}. Wpis {entry_id} pozostaje na razie w bazie.")
            continue

        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Rola czasowa wygasła")
                print(f"Usunięto czasową rolę {role.name} użytkownikowi {member.name} na serwerze {guild.name}.")
                try:
                    await member.send(f"Twoja czasowa rola **{role.name}** na serwerze **{guild.name}** wygasła i została usunięta.")
                except discord.Forbidden:
                    print(f"Nie udało się wysłać PW do {member.name} o wygaśnięciu roli.")
                database.remove_timed_role(entry_id)
            except discord.Forbidden:
                print(f"Błąd uprawnień (check_expired_roles): Nie udało się usunąć roli {role.name} od {member.name}. Wpis {entry_id} pozostaje.")
            except Exception as e:
                print(f"Nieoczekiwany błąd podczas usuwania roli {role.name} od {member.name}: {e}. Wpis {entry_id} pozostaje.")
        else:
            # Rola już została usunięta lub użytkownik jej nie miał z jakiegoś powodu
            print(f"Rola {role.name} nie była już u użytkownika {member.name} na serwerze {guild.name}. Usuwam wpis {entry_id}.")
            database.remove_timed_role(entry_id)

# Modyfikacja on_ready, aby uruchomić task
_on_ready_original = bot.on_ready

async def on_ready_with_tasks():
    await _on_ready_original() # Wywołaj oryginalną logikę on_ready
    if not check_expired_roles.is_running():
        check_expired_roles.start()
        print("Uruchomiono zadanie 'check_expired_roles'.")

bot.on_ready = on_ready_with_tasks

# --- Role za Aktywność ---

@bot.tree.command(name="add_activity_role", description="Dodaje lub aktualizuje konfigurację roli za aktywność (liczbę wiadomości).")
@app_commands.describe(rola="Rola do nadania za aktywność",
                       liczba_wiadomosci="Wymagana liczba wiadomości do otrzymania tej roli")
@app_commands.checks.has_permissions(manage_roles=True, administrator=True) # Załóżmy, że admin lub manage_roles
async def add_activity_role_command(interaction: discord.Interaction, rola: discord.Role, liczba_wiadomosci: int):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    if liczba_wiadomosci <= 0:
        await interaction.response.send_message("Liczba wiadomości musi być dodatnia.", ephemeral=True)
        return

    # Sprawdzenie hierarchii roli bota (czy może nadać tę rolę)
    if interaction.guild.me.top_role <= rola:
        await interaction.response.send_message(
            f"Nie mogę skonfigurować roli {rola.mention}, ponieważ jest ona na tym samym lub wyższym poziomie w hierarchii niż moja najwyższa rola. "
            "Bot musi mieć możliwość zarządzania tą rolą.",
            ephemeral=True
        )
        return

    try:
        database.add_activity_role_config(interaction.guild_id, rola.id, liczba_wiadomosci)
        await interaction.response.send_message(
            f"Skonfigurowano rolę {rola.mention} do nadania po wysłaniu {liczba_wiadomosci} wiadomości.",
            ephemeral=True
        )
    except sqlite3.IntegrityError:
        # Sprawdź, czy to konflikt dla roli czy dla liczby wiadomości
        configs = database.get_activity_role_configs(interaction.guild_id)
        role_conflict = any(c['role_id'] == rola.id for c in configs)
        count_conflict = any(c['required_message_count'] == liczba_wiadomosci for c in configs)

        if role_conflict:
             await interaction.response.send_message(
                f"Rola {rola.mention} jest już skonfigurowana dla innej liczby wiadomości. "
                "Usuń najpierw starą konfigurację dla tej roli, jeśli chcesz ją zmienić.",
                ephemeral=True
            )
        elif count_conflict:
            await interaction.response.send_message(
                f"Liczba wiadomości ({liczba_wiadomosci}) jest już przypisana do innej roli. "
                "Każdy próg wiadomości może być przypisany tylko do jednej roli.",
                ephemeral=True
            )
        else: # Inny, nieoczekiwany błąd integralności
            await interaction.response.send_message("Wystąpił błąd podczas zapisu konfiguracji (błąd integralności). Sprawdź logi.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił nieoczekiwany błąd: {e}", ephemeral=True)
        print(f"Błąd w /add_activity_role: {e}")

@add_activity_role_command.error
async def add_activity_role_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz wystarczających uprawnień (Administrator lub Zarządzanie Rolami) do użycia tej komendy.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"Wystąpił błąd: {error}", ephemeral=True)
        print(f"Błąd w add_activity_role_error: {error}")


@bot.tree.command(name="remove_activity_role", description="Usuwa konfigurację roli za aktywność.")
@app_commands.describe(rola="Rola, której konfigurację usunąć")
@app_commands.checks.has_permissions(manage_roles=True, administrator=True)
async def remove_activity_role_command(interaction: discord.Interaction, rola: discord.Role):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    if database.remove_activity_role_config(interaction.guild_id, rola.id):
        await interaction.response.send_message(
            f"Usunięto konfigurację roli za aktywność dla {rola.mention}.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"Rola {rola.mention} nie była skonfigurowana jako rola za aktywność.",
            ephemeral=True
        )

@remove_activity_role_command.error
async def remove_activity_role_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz wystarczających uprawnień (Administrator lub Zarządzanie Rolami) do użycia tej komendy.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"Wystąpił błąd: {error}", ephemeral=True)
        print(f"Błąd w remove_activity_role_error: {error}")


@bot.tree.command(name="list_activity_roles", description="Wyświetla skonfigurowane role za aktywność.")
async def list_activity_roles_command(interaction: discord.Interaction):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    configs = database.get_activity_role_configs(interaction.guild_id)
    if not configs:
        await interaction.response.send_message("Brak skonfigurowanych ról za aktywność na tym serwerze.", ephemeral=True)
        return

    embed = discord.Embed(title="Skonfigurowane Role za Aktywność", color=discord.Color.blue())
    description = ""
    for config in configs: # configs są posortowane ASC wg required_message_count
        role = interaction.guild.get_role(config['role_id'])
        role_mention = role.mention if role else f"ID: {config['role_id']} (usunięta?)"
        description += f"{role_mention} - Wymagane: {config['required_message_count']} wiadomości\n"

    embed.description = description
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Event handler dla nowych wiadomości (śledzenie aktywności)
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild: # Ignoruj boty i wiadomości prywatne
        # Jeśli chcemy przetwarzać komendy, które mogą być wysyłane w DM, to `not message.guild` trzeba by usunąć
        # Ale dla ról za aktywność na serwerze, guild jest potrzebny.
        # Dodatkowo, jeśli używamy `commands.Bot` i mamy prefix, bot sam powinien ignorować wiadomości niebędące komendami.
        # Jednakże, chcemy przetwarzać KAŻDĄ wiadomość dla licznika, więc nie możemy polegać na `process_commands`.
        # Jeśli mamy komendy tekstowe, musimy je wywołać ręcznie, jeśli nie są automatycznie przetwarzane.
        # Na razie zakładamy, że nie mamy innych komend tekstowych lub są one obsługiwane inaczej.
        # await bot.process_commands(message) # Jeśli potrzebne dla innych komend tekstowych
        return

    # Inkrementacja licznika wiadomości
    database.increment_message_count(message.guild.id, message.author.id)
    current_message_count = database.get_message_count(message.guild.id, message.author.id)

    # Sprawdzenie, czy użytkownik kwalifikuje się na nową rolę
    eligible_role_data = database.get_highest_eligible_role(message.guild.id, current_message_count)

    if eligible_role_data:
        eligible_role_id = eligible_role_data['role_id']
        eligible_role_object = message.guild.get_role(eligible_role_id)

        if not eligible_role_object:
            print(f"Błąd (on_message): Skonfigurowana rola za aktywność o ID {eligible_role_id} nie istnieje na serwerze {message.guild.name}.")
            return

        member = message.author # message.author to już discord.Member w kontekście serwera

        # Sprawdzenie, czy bot może zarządzać tą rolą
        if message.guild.me.top_role <= eligible_role_object:
            print(f"Ostrzeżenie (on_message): Bot nie może zarządzać rolą {eligible_role_object.name} na serwerze {message.guild.name} (hierarchia).")
            return
        if not message.guild.me.guild_permissions.manage_roles:
            print(f"Ostrzeżenie (on_message): Bot nie ma uprawnień do zarządzania rolami na serwerze {message.guild.name}.")
            return

        # Sprawdzenie, czy użytkownik już ma tę rolę
        if eligible_role_object in member.roles:
            return # Użytkownik już ma najwyższą kwalifikującą się rolę, nic nie rób

        # Przygotowanie do usunięcia innych ról za aktywność
        all_activity_role_configs = database.get_activity_role_configs(message.guild.id)
        activity_role_ids_to_potentially_remove = {config['role_id'] for config in all_activity_role_configs if config['role_id'] != eligible_role_id}

        roles_to_remove_objects = []
        for role_in_member_roles in member.roles:
            if role_in_member_roles.id in activity_role_ids_to_potentially_remove:
                # Dodatkowe sprawdzenie hierarchii dla każdej usuwanej roli (choć jeśli możemy nadać eligible_role, to pewnie i te możemy usunąć)
                if message.guild.me.top_role > role_in_member_roles:
                    roles_to_remove_objects.append(role_in_member_roles)
                else:
                    print(f"Ostrzeżenie (on_message): Bot nie może usunąć roli {role_in_member_roles.name} (hierarchia) użytkownikowi {member.name}.")


        try:
            if roles_to_remove_objects:
                await member.remove_roles(*roles_to_remove_objects, reason="Automatyczna zmiana roli za aktywność")
                print(f"Usunięto role {', '.join(r.name for r in roles_to_remove_objects)} użytkownikowi {member.name} przed nadaniem nowej roli za aktywność.")

            await member.add_roles(eligible_role_object, reason="Automatyczne nadanie roli za aktywność")
            print(f"Nadano rolę {eligible_role_object.name} użytkownikowi {member.name} za osiągnięcie {current_message_count} wiadomości.")
            try:
                await member.send(f"Gratulacje! Otrzymałeś/aś rolę **{eligible_role_object.name}** na serwerze **{message.guild.name}** za swoją aktywność!")
            except discord.Forbidden:
                print(f"Nie udało się wysłać PW do {member.name} o nowej roli za aktywność.")

        except discord.Forbidden:
            print(f"Błąd uprawnień (on_message): Nie udało się nadać/usunąć roli za aktywność użytkownikowi {member.name}.")
        except Exception as e:
            print(f"Nieoczekiwany błąd w on_message podczas zarządzania rolami za aktywność: {e}")

    # Ważne: Jeśli masz inne komendy tekstowe (zaczynające się od prefixu),
    # musisz wywołać bot.process_commands(message) na końcu tego eventu,
    # aby bot mógł je przetworzyć. Jeśli używasz tylko komend slash, to nie jest konieczne.
    # Jeśli `on_message` jest zdefiniowany, to blokuje automatyczne wywoływanie komend tekstowych.

    # --- Logika XP i Poziomów ---
    # Upewnij się, że importujesz 'leveling' i 'random' na górze pliku main.py
    # import leveling
    # import random
    # last_xp_gain_timestamp = {} # Przenieś to na poziom globalny modułu main.py, jeśli jeszcze nie istnieje

    if message.guild and not message.author.bot: # Sprawdzenie, czy wiadomość jest z serwera i nie od bota
        guild_id = message.guild.id
        user_id = message.author.id
        current_time = time.time()

        # Cooldown dla XP
        user_cooldown_key = (guild_id, user_id)
        last_gain = last_xp_gain_timestamp.get(user_cooldown_key, 0)

        if current_time - last_gain > leveling.XP_COOLDOWN_SECONDS:
            xp_to_add = random.randint(leveling.XP_PER_MESSAGE_MIN, leveling.XP_PER_MESSAGE_MAX)
            new_total_xp = database.add_xp(guild_id, user_id, xp_to_add)
            last_xp_gain_timestamp[user_cooldown_key] = current_time

            # print(f"User {message.author.name} gained {xp_to_add} XP. Total XP: {new_total_xp}") # Logowanie przyznania XP

            user_stats = database.get_user_stats(guild_id, user_id)
            current_level_db = user_stats['level']

            calculated_level = leveling.get_level_from_xp(new_total_xp)

            if calculated_level > current_level_db:
                database.set_user_level(guild_id, user_id, calculated_level)
                try:
                    # Wysłanie wiadomości o awansie na kanale, gdzie padła ostatnia wiadomość
                    # Można to też wysłać w PW lub na dedykowany kanał
                    await message.channel.send(
                        f"🎉 Gratulacje {message.author.mention}! Osiągnąłeś/aś **Poziom {calculated_level}**!"
                    )
                    print(f"User {message.author.name} leveled up to {calculated_level} on server {message.guild.name}.")
                except discord.Forbidden:
                    print(f"Nie udało się wysłać wiadomości o awansie na kanale {message.channel.name} (brak uprawnień).")
                except Exception as e:
                    print(f"Nieoczekiwany błąd podczas wysyłania wiadomości o awansie: {e}")

    # Jeśli używasz komend tekstowych z prefixem, odkomentuj poniższe:
    # await bot.process_commands(message)

# Komenda /rank
@bot.tree.command(name="rank", description="Wyświetla Twój aktualny poziom i postęp XP (lub innego użytkownika).")
@app_commands.describe(uzytkownik="Użytkownik, którego statystyki chcesz zobaczyć (opcjonalnie).")
async def rank_command(interaction: discord.Interaction, uzytkownik: discord.Member = None):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    target_user = uzytkownik if uzytkownik else interaction.user

    # Upewnij się, że target_user to Member, a nie User, jeśli pochodzi z interaction.user
    if not isinstance(target_user, discord.Member):
        target_user = interaction.guild.get_member(target_user.id)
        if not target_user:
            await interaction.response.send_message("Nie udało się znaleźć tego użytkownika na serwerze.", ephemeral=True)
            return


    user_stats = database.get_user_stats(interaction.guild_id, target_user.id)
    current_level = user_stats['level']
    current_xp = user_stats['xp']

    xp_for_current_level_gate = leveling.total_xp_for_level(current_level)
    xp_for_next_level_gate = leveling.total_xp_for_level(current_level + 1)

    xp_in_current_level = current_xp - xp_for_current_level_gate
    xp_needed_for_next_level_up = xp_for_next_level_gate - xp_for_current_level_gate

    # Zapobieganie dzieleniu przez zero, jeśli xp_for_level_up(current_level + 1) zwróci 0 (np. max level)
    # lub jeśli current_level = 0 i xp_for_next_level_gate jest progiem dla level 1
    if xp_needed_for_next_level_up == 0 and current_level > 0 : # Osiągnięto jakiś maksymalny skonfigurowany poziom
        progress_percentage = 100.0
        progress_bar = "█" * 10 # Pełny pasek
        xp_display = f"{current_xp} XP (MAX POZIOM)"
    elif xp_needed_for_next_level_up == 0 and current_level == 0: # Poziom 0, próg do poziomu 1 to xp_for_next_level_gate
        if xp_for_next_level_gate == 0: # Sytuacja awaryjna, nie powinno się zdarzyć przy dobrej formule
             progress_percentage = 0.0
        else:
            progress_percentage = (current_xp / xp_for_next_level_gate) * 100
        progress_bar_filled_count = int(progress_percentage / 10)
        progress_bar = "█" * progress_bar_filled_count + "░" * (10 - progress_bar_filled_count)
        xp_display = f"{current_xp} / {xp_for_next_level_gate} XP"

    else:
        progress_percentage = (xp_in_current_level / xp_needed_for_next_level_up) * 100
        progress_bar_filled_count = int(progress_percentage / 10)
        progress_bar = "█" * progress_bar_filled_count + "░" * (10 - progress_bar_filled_count)
        xp_display = f"{xp_in_current_level} / {xp_needed_for_next_level_up} XP na tym poziomie"


    embed = discord.Embed(
        title=f"Statystyki Aktywności dla {target_user.display_name}",
        color=discord.Color.green() if target_user == interaction.user else discord.Color.blue()
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="Poziom", value=f"**{current_level}**", inline=True)
    embed.add_field(name="Całkowite XP", value=f"**{current_xp}**", inline=True)

    embed.add_field(
        name=f"Postęp do Poziomu {current_level + 1}",
        value=f"{progress_bar} ({progress_percentage:.2f}%)\n{xp_display}",
        inline=False
    )
    # Można dodać ranking globalny/serwerowy jeśli zaimplementowany
    # embed.add_field(name="Ranking na serwerze", value="#X (TODO)", inline=True)

    await interaction.response.send_message(embed=embed)

# --- System Weryfikacji Quizem ---

@bot.tree.command(name="set_unverified_role", description="Ustawia rolę dla nowych, nieweryfikowanych członków.")
@app_commands.describe(rola="Rola, którą otrzymają nowi członkowie przed weryfikacją.")
@app_commands.checks.has_permissions(administrator=True)
async def set_unverified_role_command(interaction: discord.Interaction, rola: discord.Role):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    try:
        database.update_server_config(guild_id=interaction.guild_id, unverified_role_id=rola.id)
        await interaction.response.send_message(f"Rola dla nieweryfikowanych członków została ustawiona na {rola.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd podczas ustawiania roli: {e}", ephemeral=True)

@set_unverified_role_command.error
async def set_unverified_role_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora, aby użyć tej komendy.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)

# --- Komendy Konfiguracyjne Moderacji ---

@bot.tree.command(name="set_modlog_channel", description="Ustawia kanał, na który będą wysyłane logi moderacyjne.")
@app_commands.describe(kanal="Kanał tekstowy dla logów moderacyjnych.")
@app_commands.checks.has_permissions(administrator=True)
async def set_modlog_channel_command(interaction: discord.Interaction, kanal: discord.TextChannel):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    try:
        database.update_server_config(guild_id=interaction.guild_id, moderation_log_channel_id=kanal.id)
        await interaction.response.send_message(f"Kanał logów moderacyjnych został ustawiony na {kanal.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd podczas ustawiania kanału: {e}", ephemeral=True)

@set_modlog_channel_command.error
async def set_modlog_channel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.tree.command(name="add_banned_word", description="Dodaje słowo lub frazę do czarnej listy (filtr wulgaryzmów).")
@app_commands.describe(slowo="Słowo lub fraza do zablokowania (wielkość liter ignorowana).")
@app_commands.checks.has_permissions(administrator=True)
async def add_banned_word_command(interaction: discord.Interaction, slowo: str):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    normalized_word = slowo.lower().strip()
    if not normalized_word:
        await interaction.response.send_message("Słowo nie może być puste.", ephemeral=True)
        return

    if database.add_banned_word(interaction.guild_id, normalized_word):
        await interaction.response.send_message(f"Słowo/fraza \"{normalized_word}\" została dodana do czarnej listy.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Słowo/fraza \"{normalized_word}\" już jest na czarnej liście.", ephemeral=True)

@add_banned_word_command.error
async def add_banned_word_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.tree.command(name="remove_banned_word", description="Usuwa słowo lub frazę z czarnej listy.")
@app_commands.describe(slowo="Słowo lub fraza do usunięcia (wielkość liter ignorowana).")
@app_commands.checks.has_permissions(administrator=True)
async def remove_banned_word_command(interaction: discord.Interaction, slowo: str):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    normalized_word = slowo.lower().strip()
    if not normalized_word:
        await interaction.response.send_message("Słowo nie może być puste.", ephemeral=True)
        return

    if database.remove_banned_word(interaction.guild_id, normalized_word):
        await interaction.response.send_message(f"Słowo/fraza \"{normalized_word}\" została usunięta z czarnej listy.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Słowa/frazy \"{normalized_word}\" nie było na czarnej liście.", ephemeral=True)

@remove_banned_word_command.error
async def remove_banned_word_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.tree.command(name="list_banned_words", description="Wyświetla listę zakazanych słów/fraz.")
@app_commands.checks.has_permissions(administrator=True)
async def list_banned_words_command(interaction: discord.Interaction):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    words = database.get_banned_words(interaction.guild_id)
    if not words:
        await interaction.response.send_message("Czarna lista słów jest pusta.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Czarna Lista Słów dla {interaction.guild.name}", color=discord.Color.red())
    # Paginacja dla długiej listy
    description_parts = []
    current_part = ""
    for word in sorted(words):
        if len(current_part) + len(word) + 2 > 1900: # Zostaw trochę miejsca na formatowanie i ewentualne znaki nowej linii
            description_parts.append(current_part)
            current_part = ""
        current_part += f"- {word}\n"
    description_parts.append(current_part) # Dodaj ostatnią część

    first_embed_sent = False
    for i, part in enumerate(description_parts):
        if not part.strip(): continue # Pomiń puste części

        part_title = embed.title if i == 0 else f"{embed.title} (cd.)"
        page_embed = discord.Embed(title=part_title, description=part, color=discord.Color.red())

        if not first_embed_sent:
            await interaction.response.send_message(embed=page_embed, ephemeral=True)
            first_embed_sent = True
        else:
            await interaction.followup.send(embed=page_embed, ephemeral=True)

    if not first_embed_sent: # Jeśli lista była pusta po sortowaniu/filtrowaniu (np. same puste słowa)
         await interaction.response.send_message("Czarna lista słów jest pusta lub zawiera tylko puste wpisy.", ephemeral=True)


@list_banned_words_command.error
async def list_banned_words_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.tree.command(name="toggle_filter", description="Włącza lub wyłącza określony filtr moderacyjny.")
@app_commands.describe(filtr="Nazwa filtru do przełączenia.", status="Nowy status filtru (on/off).")
@app_commands.choices(filtr=[
    app_commands.Choice(name="Wulgaryzmy (Profanity)", value="profanity"),
    app_commands.Choice(name="Spam", value="spam"),
    app_commands.Choice(name="Linki Zapraszające (Invites)", value="invites"),
])
@app_commands.choices(status=[
    app_commands.Choice(name="Włączony (On)", value="on"),
    app_commands.Choice(name="Wyłączony (Off)", value="off"),
])
@app_commands.checks.has_permissions(administrator=True)
async def toggle_filter_command(interaction: discord.Interaction, filtr: app_commands.Choice[str], status: app_commands.Choice[str]):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    new_status_bool = status.value == "on"
    filter_name_db = ""
    filter_name_display = filtr.name

    if filtr.value == "profanity":
        filter_name_db = "filter_profanity_enabled"
    elif filtr.value == "spam":
        filter_name_db = "filter_spam_enabled"
    elif filtr.value == "invites":
        filter_name_db = "filter_invites_enabled"
    else:
        await interaction.response.send_message("Nieznany typ filtru.", ephemeral=True)
        return

    try:
        update_kwargs = {filter_name_db: new_status_bool}
        database.update_server_config(guild_id=interaction.guild_id, **update_kwargs)
        await interaction.response.send_message(f"Filtr '{filter_name_display}' został {'włączony' if new_status_bool else 'wyłączony'}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd podczas aktualizacji statusu filtru: {e}", ephemeral=True)

@toggle_filter_command.error
async def toggle_filter_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.tree.command(name="moderation_settings", description="Wyświetla aktualne ustawienia moderacji serwera.")
@app_commands.checks.has_permissions(administrator=True)
async def moderation_settings_command(interaction: discord.Interaction):
    if not interaction.guild_id or not interaction.guild:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    config = database.get_server_config(interaction.guild_id)
    if not config: # Powinno być utworzone przez INSERT OR IGNORE w update_server_config
        # Ale get_server_config zwraca domyślne wartości jeśli niektóre pola są None,
        # a None jeśli w ogóle nie ma wpisu dla guild_id.
        # Zakładając, że wpis istnieje, ale wartości mogą być None (co get_server_config obsługuje dając default)
        # Jeśli config jest None, to znaczy, że nawet INSERT OR IGNORE nie zadziałał lub nie było żadnej interakcji z configiem.
        # Możemy stworzyć tu domyślny config dla celów wyświetlania lub poinformować, że nic nie ustawiono.
        # Dla bezpieczeństwa, jeśli config is None, to znaczy, że nie ma wpisu.
         database.update_server_config(interaction.guild_id) # Utwórz domyślny wpis
         config = database.get_server_config(interaction.guild_id) # Pobierz ponownie

    log_channel = interaction.guild.get_channel(config.get("moderation_log_channel_id")) if config.get("moderation_log_channel_id") else "Nie ustawiono"

    embed = discord.Embed(title=f"Ustawienia Moderacji dla {interaction.guild.name}", color=discord.Color.gold())
    embed.add_field(name="Kanał Logów Moderacyjnych", value=log_channel.mention if isinstance(log_channel, discord.TextChannel) else str(log_channel), inline=False)
    embed.add_field(name="Filtr Wulgaryzmów", value="✅ Włączony" if config.get("filter_profanity_enabled", True) else "❌ Wyłączony", inline=True)
    embed.add_field(name="Filtr Spamu", value="✅ Włączony" if config.get("filter_spam_enabled", True) else "❌ Wyłączony", inline=True)
    embed.add_field(name="Filtr Linków Zapraszających", value="✅ Włączony" if config.get("filter_invites_enabled", True) else "❌ Wyłączony", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@moderation_settings_command.error
async def moderation_settings_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)

# Event dla dołączającego użytkownika - nadanie roli Nieweryfikowany
@bot.event
async def on_member_join(member: discord.Member):
    if member.bot: # Ignoruj inne boty dołączające do serwera
        return

    guild = member.guild
    server_config = database.get_server_config(guild.id)

    if server_config and server_config.get("unverified_role_id"):
        unverified_role_id = server_config["unverified_role_id"]
        role = guild.get_role(unverified_role_id)
        if role:
            try:
                # Sprawdzenie hierarchii - czy bot może nadać tę rolę
                if guild.me.top_role > role:
                    await member.add_roles(role, reason="Automatyczne nadanie roli dla nowych członków.")
                    print(f"Nadano rolę '{role.name}' nowemu członkowi {member.name} na serwerze {guild.name}.")

                    # Wysłanie wiadomości powitalnej/instrukcji
                    welcome_message = (
                        f"Witaj {member.mention} na serwerze **{guild.name}**!\n\n"
                        "Aby uzyskać pełny dostęp, musisz przejść krótką weryfikację w formie quizu regulaminowego.\n"
                        "Użyj komendy `/verify_me` tutaj (w DM) lub na dowolnym kanale na serwerze, aby rozpocząć quiz."
                    )
                    # Spróbuj wysłać w DM
                    try:
                        await member.send(welcome_message)
                        print(f"Wysłano wiadomość powitalną DM do {member.name}.")
                    except discord.Forbidden:
                        print(f"Nie udało się wysłać wiadomości powitalnej DM do {member.name} (zablokowane DM lub brak uprawnień).")
                        # Można dodać fallback na wysłanie na kanał systemowy serwera, jeśli istnieje i jest skonfigurowany
                        # np. if guild.system_channel: await guild.system_channel.send(f"Witaj {member.mention}! Użyj /verify_me aby się zweryfikować.")
                    except Exception as e_dm:
                        print(f"Inny błąd podczas wysyłania DM do {member.name}: {e_dm}")

                else:
                    print(f"Błąd (on_member_join): Bot nie może nadać roli '{role.name}' (ID: {unverified_role_id}) użytkownikowi {member.name} na serwerze {guild.name} z powodu niewystarczającej hierarchii roli bota.")
            except discord.Forbidden:
                print(f"Błąd (on_member_join): Bot nie ma uprawnień do nadania roli '{role.name}' (ID: {unverified_role_id}) na serwerze {guild.name}.")
            except Exception as e:
                print(f"Nieoczekiwany błąd (on_member_join) podczas nadawania roli {member.name} na serwerze {guild.name}: {e}")
        else:
            print(f"Błąd (on_member_join): Skonfigurowana rola 'Nieweryfikowany' (ID: {unverified_role_id}) nie została znaleziona na serwerze {guild.name}.")
    # Jeśli nie ma konfiguracji unverified_role_id, nic nie rób (lub zaloguj ostrzeżenie)
    # else:
    #     print(f"Ostrzeżenie (on_member_join): Brak skonfigurowanej roli 'Nieweryfikowany' dla serwera {guild.name}.")

    # Jeśli masz inne zadania do wykonania przy dołączeniu członka, dodaj je tutaj.
    # Np. jeśli `on_message` przetwarza komendy tekstowe, a nie tylko slash, to nie jest to miejsce na `process_commands`.

# Globalny słownik do śledzenia stanu quizu użytkowników
# Klucz: user_id, Wartość: {'guild_id': int, 'questions': list, 'current_q_index': int, 'answers': list}
active_quizzes = {}

@bot.tree.command(name="verify_me", description="Rozpoczyna quiz weryfikacyjny, aby uzyskać dostęp do serwera.")
async def verify_me_command(interaction: discord.Interaction):
    if not interaction.guild: # Ta komenda inicjuje proces dla serwera, więc musi być info o guild
        await interaction.response.send_message(
            "Proszę, użyj tej komendy na serwerze, którego dotyczy weryfikacja, lub upewnij się, że bot wie, który serwer weryfikujesz.",
            ephemeral=True
        )
        return

    user = interaction.user
    guild = interaction.guild

    # Sprawdzenie, czy użytkownik jest już zweryfikowany
    server_config = database.get_server_config(guild.id)
    if not server_config or not server_config.get("verified_role_id") or not server_config.get("unverified_role_id"):
        await interaction.response.send_message(
            "System weryfikacji nie jest w pełni skonfigurowany na tym serwerze. Skontaktuj się z administratorem.",
            ephemeral=True
        )
        return

    verified_role = guild.get_role(server_config["verified_role_id"])
    unverified_role = guild.get_role(server_config["unverified_role_id"])

    if not verified_role or not unverified_role:
        await interaction.response.send_message(
            "Role weryfikacyjne (zweryfikowany/nieweryfikowany) nie są poprawnie skonfigurowane. Skontaktuj się z administratorem.",
            ephemeral=True
        )
        return

    member = guild.get_member(user.id)
    if not member: # Powinno być, jeśli interakcja z serwera
        await interaction.response.send_message("Nie mogę Cię znaleźć na tym serwerze.", ephemeral=True)
        return

    if verified_role in member.roles:
        await interaction.response.send_message("Jesteś już zweryfikowany/a!", ephemeral=True)
        return

    if not (unverified_role in member.roles):
        # Jeśli użytkownik nie ma roli "unverified", a także nie ma "verified", to jest to dziwny stan.
        # Możemy założyć, że nie potrzebuje weryfikacji, lub że admin powinien to naprawić.
        # Na razie, jeśli nie ma unverified, a ma inne role, niech admin to sortuje.
        # Jeśli nie ma unverified i nie ma verified, a są pytania - może zacząć.
        # Dla uproszczenia: jeśli nie masz roli "unverified", a quiz jest, to coś jest nie tak z setupem.
        # Ale jeśli nie masz "unverified" I NIE MASZ "verified", to przepuśćmy do quizu.
         pass # Pozwól kontynuować, jeśli nie ma ani verified, ani unverified.

    if user.id in active_quizzes:
        await interaction.response.send_message("Masz już aktywny quiz. Sprawdź swoje wiadomości prywatne.", ephemeral=True)
        return

    questions = database.get_quiz_questions(guild.id)
    if not questions:
        await interaction.response.send_message(
            "Brak pytań w quizie weryfikacyjnym dla tego serwera. Skontaktuj się z administratorem.",
            ephemeral=True
        )
        # Można też automatycznie zweryfikować, jeśli nie ma pytań, a role są ustawione.
        # Ale to może być niebezpieczne, jeśli admin zapomniał dodać pytań.
        # Lepiej poczekać na konfigurację.
        return

    active_quizzes[user.id] = {
        "guild_id": guild.id,
        "questions": questions,
        "current_q_index": 0,
        "answers": []
    }

    await interaction.response.send_message("Rozpoczynam quiz weryfikacyjny w Twoich wiadomościach prywatnych (DM). Sprawdź je teraz!", ephemeral=True)

    try:
        await send_quiz_question_dm(user)
    except discord.Forbidden:
        await interaction.followup.send("Nie mogę wysłać Ci wiadomości prywatnej. Upewnij się, że masz włączone DM od członków serwera.", ephemeral=True)
        del active_quizzes[user.id] # Usuń stan quizu, bo nie można kontynuować
    except Exception as e:
        await interaction.followup.send(f"Wystąpił błąd podczas rozpoczynania quizu: {e}", ephemeral=True)
        if user.id in active_quizzes:
            del active_quizzes[user.id]


async def send_quiz_question_dm(user: discord.User):
    quiz_state = active_quizzes.get(user.id)
    if not quiz_state:
        return # Quiz nie jest już aktywny

    q_index = quiz_state["current_q_index"]
    if q_index < len(quiz_state["questions"]):
        question_data = quiz_state["questions"][q_index]
        try:
            await user.send(f"**Pytanie {q_index + 1}/{len(quiz_state['questions'])}:**\n{question_data['question']}")
        except discord.Forbidden:
            # Jeśli nie można wysłać DM, zakończ quiz dla tego użytkownika
            guild_id_for_log = quiz_state.get('guild_id', 'Nieznany')
            print(f"Błąd DM (send_quiz_question_dm): Nie można wysłać pytania do {user.name} (ID: {user.id}) dla serwera {guild_id_for_log}. Kończenie quizu.")
            if user.id in active_quizzes: del active_quizzes[user.id]
            # TODO: Można by wysłać wiadomość na serwerze, jeśli to możliwe, że DM są zablokowane.
        except Exception as e:
            print(f"Błąd podczas wysyłania pytania DM do {user.name}: {e}")
            if user.id in active_quizzes: del active_quizzes[user.id]
    else:
        # Wszystkie pytania zadane, czas na sprawdzenie
        await process_quiz_results(user)


async def process_quiz_results(user: discord.User):
    quiz_state = active_quizzes.get(user.id)
    if not quiz_state:
        return

    guild_id = quiz_state["guild_id"]
    guild = bot.get_guild(guild_id)
    if not guild:
        print(f"Błąd (process_quiz_results): Nie znaleziono serwera o ID {guild_id} dla użytkownika {user.name}.")
        if user.id in active_quizzes: del active_quizzes[user.id]
        return

    member = guild.get_member(user.id)
    if not member:
        print(f"Błąd (process_quiz_results): Nie znaleziono członka {user.name} na serwerze {guild.name}.")
        if user.id in active_quizzes: del active_quizzes[user.id]
        return

    server_config = database.get_server_config(guild.id)
    if not server_config or not server_config.get("verified_role_id") or not server_config.get("unverified_role_id"):
        await user.send("Wystąpił błąd konfiguracyjny na serwerze. Nie można zakończyć weryfikacji.")
        if user.id in active_quizzes: del active_quizzes[user.id]
        return

    unverified_role = guild.get_role(server_config["unverified_role_id"])
    verified_role = guild.get_role(server_config["verified_role_id"])

    if not unverified_role or not verified_role:
        await user.send("Role weryfikacyjne nie są poprawnie ustawione na serwerze. Skontaktuj się z administratorem.")
        if user.id in active_quizzes: del active_quizzes[user.id]
        return

    correct_answers_count = 0
    for i, question_data in enumerate(quiz_state["questions"]):
        user_answer = quiz_state["answers"][i].lower().strip()
        correct_answer = question_data["answer"].lower().strip() # Odpowiedzi w bazie są już małymi literami
        if user_answer == correct_answer:
            correct_answers_count += 1

    all_correct = correct_answers_count == len(quiz_state["questions"])

    if all_correct:
        try:
            # Sprawdzenie hierarchii przed zmianą ról
            if guild.me.top_role > verified_role and (guild.me.top_role > unverified_role or unverified_role not in member.roles):
                if unverified_role in member.roles:
                    await member.remove_roles(unverified_role, reason="Pomyślna weryfikacja quizem.")
                await member.add_roles(verified_role, reason="Pomyślna weryfikacja quizem.")
                await user.send(
                    f"🎉 Gratulacje! Pomyślnie przeszedłeś/aś quiz weryfikacyjny na serwerze **{guild.name}**!\n"
                    f"Otrzymałeś/aś rolę {verified_role.mention} i pełny dostęp."
                )
                print(f"Użytkownik {member.name} pomyślnie zweryfikowany na serwerze {guild.name}.")
            else:
                await user.send(f"Weryfikacja przebiegła pomyślnie, ale nie mogę zarządzać Twoimi rolami (problem z hierarchią ról bota). Skontaktuj się z administratorem serwera **{guild.name}**.")
                print(f"Problem z hierarchią ról przy weryfikacji {member.name} na {guild.name}.")

        except discord.Forbidden:
            await user.send(f"Weryfikacja przebiegła pomyślnie, ale nie mam uprawnień do zmiany Twoich ról na serwerze **{guild.name}**. Skontaktuj się z administratorem.")
            print(f"Problem z uprawnieniami przy weryfikacji {member.name} na {guild.name}.")
        except Exception as e:
            await user.send(f"Wystąpił nieoczekiwany błąd podczas finalizacji weryfikacji na serwerze **{guild.name}**. Skontaktuj się z administratorem. Błąd: {e}")
            print(f"Nieoczekiwany błąd przy weryfikacji {member.name} na {guild.name}: {e}")
    else:
        # TODO: Dodać logikę dla niepoprawnych odpowiedzi, np. ile było poprawnych, czy można spróbować ponownie.
        await user.send(
            f"Niestety, nie wszystkie Twoje odpowiedzi były poprawne ({correct_answers_count}/{len(quiz_state['questions'])}).\n"
            "Spróbuj ponownie używając komendy `/verify_me` na serwerze."
        )
        print(f"Użytkownik {member.name} nie przeszedł weryfikacji na serwerze {guild.name} ({correct_answers_count}/{len(quiz_state['questions'])}).")

    if user.id in active_quizzes:
        del active_quizzes[user.id] # Zakończ sesję quizu


# Modyfikacja on_message, aby przechwytywać odpowiedzi na quiz w DM
_on_message_original = bot.on_message

async def on_message_with_quiz(message: discord.Message):
    # Najpierw wywołaj oryginalną logikę on_message (dla XP, ról za aktywność itp.)
    # ale tylko jeśli to nie jest DM i nie jest to odpowiedź na quiz
    if message.guild and not (message.author.id in active_quizzes and isinstance(message.channel, discord.DMChannel)):
        # To jest nieco skomplikowane, bo oryginalny on_message też ma logikę dla guild
        # Musimy uważać, żeby nie wywołać go podwójnie lub w złym kontekście.
        # Na razie załóżmy, że oryginalny on_message jest tylko dla wiadomości na serwerze.
        # await _on_message_original(message) # To może być problematyczne, jeśli on_message_original ma własne return

        # Zamiast wywoływać cały oryginalny on_message, skopiujmy jego istotną część tutaj,
        # upewniając się, że nie koliduje z logiką DM quizu.

        # --- Skopiowana logika z on_message dla XP i ról za aktywność ---
        if message.guild and not message.author.bot: # Upewnij się, że to wiadomość na serwerze
            # Inkrementacja licznika wiadomości dla ról za aktywność (jeśli ta funkcja jest nadal używana)
            # database.increment_message_count(message.guild.id, message.author.id)
            # current_msg_count_for_activity_roles = database.get_user_stats(message.guild.id, message.author.id)['message_count']
            # eligible_activity_role_data = database.get_highest_eligible_role(message.guild.id, current_msg_count_for_activity_roles)
            # if eligible_activity_role_data: ... (reszta logiki ról za aktywność) ...

            # Logika XP i Poziomów
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
                        await message.channel.send(
                            f"🎉 Gratulacje {message.author.mention}! Osiągnąłeś/aś **Poziom {calculated_level_xp}**!"
                        )
                        print(f"User {message.author.name} leveled up to {calculated_level_xp} on server {message.guild.name}.")
                    except discord.Forbidden:
                        print(f"Nie udało się wysłać wiadomości o awansie na kanale {message.channel.name} (brak uprawnień).")
        # --- Koniec skopiowanej logiki ---

    # --- Logika Moderacji ---
    # Ta sekcja powinna być tylko dla wiadomości na serwerze (message.guild istnieje)
    # i nie od botów, i nie przetworzona już jako odpowiedź na quiz.
    # Warunek `message.guild` jest już sprawdzony na początku `on_message_with_quiz` dla logiki XP.
    # Musimy upewnić się, że nie moderujemy odpowiedzi na quiz w DM.

    # Sprawdź, czy to nie jest odpowiedź na quiz w DM, zanim przejdziesz do moderacji
    if not (isinstance(message.channel, discord.DMChannel) and message.author.id in active_quizzes):
        if message.guild and not message.author.bot:
            # Sprawdź, czy autor nie jest administratorem lub nie ma uprawnień zarządzania wiadomościami
            # (opcjonalne, aby nie moderować adminów/modów)
            # if not message.author.guild_permissions.manage_messages: # Przykład

            server_config_mod = database.get_server_config(message.guild.id)
            if not server_config_mod: # Jeśli nie ma configu, nie ma co moderować
                # await bot.process_commands(message) # Jeśli są komendy tekstowe
                return

            message_deleted = False # Flaga, aby nie przetwarzać XP jeśli wiadomość usunięta

            # 1. Filtr Wulgaryzmów
            if server_config_mod.get("filter_profanity_enabled", True) and not message_deleted:
                banned_words_list = database.get_banned_words(message.guild.id)
                if banned_words_list:
                    # Tworzymy regex, który dopasuje całe słowa, case-insensitive
                    # \b na granicach słów, aby uniknąć np. "ass" w "grass"
                    # Używamy re.escape, aby specjalne znaki w słowach były traktowane dosłownie
                    # regex_pattern = r"(?i)\b(" + "|".join(re.escape(word) for word in banned_words_list) + r")\b"
                    # Prostsze sprawdzenie:
                    for banned_word in banned_words_list:
                        # Użycie \bword\b jest dobre, ale może być wolne dla wielu słów.
                        # Prostsze: ' ' + word + ' ' lub na początku/końcu linii.
                        # Lub po prostu `if banned_word in message.content.lower():` jeśli akceptujemy częściowe dopasowania
                        # Dla bardziej precyzyjnego dopasowania całych słów, użyjemy regexu z word boundaries \b
                        # Trzeba uważać na znaki specjalne w banned_word, jeśli nie używamy re.escape
                        # Bezpieczniejsze jest iterowanie i sprawdzanie `\bword\b` dla każdego słowa.
                        # To jest bardziej odporne na znaki specjalne w słowach z bazy.
                        pattern = r"(?i)\b" + re.escape(banned_word) + r"\b"
                        if re.search(pattern, message.content):
                            try:
                                await message.delete()
                                await log_moderation_action(
                                    message.guild, message.author, message.content,
                                    f"Wykryto zakazane słowo/frazę: '{banned_word}'",
                                    message.channel, server_config_mod.get("moderation_log_channel_id")
                                )
                                message_deleted = True
                                # Można wysłać ostrzeżenie do użytkownika w DM
                                try:
                                    await message.author.send(f"Twoja wiadomość na serwerze **{message.guild.name}** została usunięta, ponieważ zawierała niedozwolone słownictwo.")
                                except discord.Forbidden:
                                    pass # Nie można wysłać DM
                                break # Przerywamy pętlę po pierwszym znalezionym słowie
                            except discord.Forbidden:
                                print(f"Błąd moderacji (profanity): Brak uprawnień do usunięcia wiadomości na {message.guild.name}.")
                            except Exception as e:
                                print(f"Błąd moderacji (profanity): {e}")
                            break

            # 2. Filtr Linków Zapraszających Discord
            if server_config_mod.get("filter_invites_enabled", True) and not message_deleted:
                invite_pattern = r"(discord\.(gg|me|io|com\/invite)\/[a-zA-Z0-9]+)"
                if re.search(invite_pattern, message.content, re.IGNORECASE):
                    try:
                        await message.delete()
                        await log_moderation_action(
                            message.guild, message.author, message.content,
                            "Wykryto link zapraszający do Discorda.",
                            message.channel, server_config_mod.get("moderation_log_channel_id")
                        )
                        message_deleted = True
                        try:
                            await message.author.send(f"Twoja wiadomość na serwerze **{message.guild.name}** została usunięta, ponieważ zawierała link zapraszający.")
                        except discord.Forbidden:
                            pass
                    except discord.Forbidden:
                        print(f"Błąd moderacji (invites): Brak uprawnień do usunięcia wiadomości na {message.guild.name}.")
                    except Exception as e:
                        print(f"Błąd moderacji (invites): {e}")

            # 3. Filtr Spamu (Podstawowy)
            if server_config_mod.get("filter_spam_enabled", True) and not message_deleted:
                # a) Powtarzające się wiadomości
                user_msgs = user_recent_messages[message.author.id]
                user_msgs.append(message.content) # deque automatycznie usunie najstarszą jeśli maxlen osiągnięty
                if len(user_msgs) == user_msgs.maxlen: # Mamy wystarczająco wiadomości do porównania
                    # Sprawdź, czy wszystkie (lub np. 2 z 3) są takie same
                    if len(set(user_msgs)) == 1: # Wszystkie wiadomości w deque są identyczne
                        try:
                            await message.delete()
                            await log_moderation_action(
                                message.guild, message.author, message.content,
                                "Wykryto powtarzające się wiadomości (spam).",
                                message.channel, server_config_mod.get("moderation_log_channel_id")
                            )
                            message_deleted = True
                            try:
                                await message.author.send(f"Twoja wiadomość na serwerze **{message.guild.name}** została usunięta z powodu spamu (powtarzanie treści).")
                            except discord.Forbidden:
                                pass
                        except discord.Forbidden:
                             print(f"Błąd moderacji (spam-repeat): Brak uprawnień do usunięcia wiadomości na {message.guild.name}.")
                        except Exception as e:
                            print(f"Błąd moderacji (spam-repeat): {e}")

                # b) Nadmierne wzmianki (jeśli wiadomość nie została już usunięta)
                if not message_deleted and (len(message.mentions) + len(message.role_mentions) > 5): # Np. próg 5 wzmianek
                    try:
                        await message.delete()
                        await log_moderation_action(
                            message.guild, message.author, message.content,
                            "Wykryto nadmierną liczbę wzmianek (spam).",
                            message.channel, server_config_mod.get("moderation_log_channel_id")
                        )
                        message_deleted = True
                        try:
                            await message.author.send(f"Twoja wiadomość na serwerze **{message.guild.name}** została usunięta z powodu nadmiernej liczby wzmianek.")
                        except discord.Forbidden:
                            pass
                    except discord.Forbidden:
                        print(f"Błąd moderacji (spam-mentions): Brak uprawnień do usunięcia wiadomości na {message.guild.name}.")
                    except Exception as e:
                        print(f"Błąd moderacji (spam-mentions): {e}")

            # Jeśli wiadomość została usunięta przez moderację, nie przyznawaj XP i nie przetwarzaj dalej dla ról za aktywność
            if message_deleted:
                # await bot.process_commands(message) # Jeśli są komendy tekstowe, mogą być nadal przetwarzane
                return


    # Logika dla odpowiedzi na quiz w DM
    if isinstance(message.channel, discord.DMChannel) and message.author.id in active_quizzes and not message.author.bot:
        user_id = message.author.id
        quiz_state = active_quizzes[user_id]

        if quiz_state["current_q_index"] >= len(quiz_state["questions"]):
             return

        quiz_state["answers"].append(message.content)
        quiz_state["current_q_index"] += 1

        await send_quiz_question_dm(message.author)
        return

    # await bot.process_commands(message)

bot.on_message = on_message_with_quiz # Nadpisz standardowy on_message


async def log_moderation_action(guild: discord.Guild, author: discord.User, deleted_content: str, reason: str,
                                channel_where_deleted: discord.TextChannel, mod_log_channel_id: int | None):
    if not mod_log_channel_id:
        return # Brak skonfigurowanego kanału logów

    log_channel = guild.get_channel(mod_log_channel_id)
    if not log_channel or not isinstance(log_channel, discord.TextChannel):
        print(f"Błąd logowania moderacji: Nie znaleziono kanału logów (ID: {mod_log_channel_id}) na serwerze {guild.name} lub nie jest to kanał tekstowy.")
        return

    embed = discord.Embed(title="Akcja Moderacyjna", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Użytkownik", value=f"{author.mention} ({author.id})", inline=False)
    embed.add_field(name="Kanał", value=channel_where_deleted.mention, inline=False)
    embed.add_field(name="Powód", value=reason, inline=False)

    # Ogranicz długość treści wiadomości w logu
    truncated_content = deleted_content
    if len(deleted_content) > 1000:
        truncated_content = deleted_content[:1000] + "..."
    embed.add_field(name="Usunięta treść", value=f"```{truncated_content}```" if truncated_content else "```(Brak treści - np. tylko załącznik)```", inline=False)

    embed.set_footer(text=f"ID Wiadomości (usuniętej): (Bot nie ma dostępu do ID po usunięciu przez siebie)") # message.id nie jest dostępne po message.delete()
    # Można by przekazać message.id do log_moderation_action PRZED message.delete(), jeśli potrzebne.

    try:
        await log_channel.send(embed=embed)
    except discord.Forbidden:
        print(f"Błąd logowania moderacji: Brak uprawnień do wysyłania wiadomości na kanale logów {log_channel.mention} na serwerze {guild.name}.")
    except Exception as e:
        print(f"Nieoczekiwany błąd podczas logowania akcji moderacyjnej: {e}")


@bot.tree.command(name="set_verified_role", description="Ustawia rolę nadawaną po pomyślnej weryfikacji quizem.")
@app_commands.describe(rola="Rola, którą otrzymają członkowie po weryfikacji.")
@app_commands.checks.has_permissions(administrator=True)
async def set_verified_role_command(interaction: discord.Interaction, rola: discord.Role):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    # Sprawdzenie hierarchii - bot musi móc nadać tę rolę
    if interaction.guild and interaction.guild.me.top_role <= rola:
        await interaction.response.send_message(
            f"Nie mogę ustawić roli {rola.mention} jako roli weryfikacyjnej, ponieważ jest ona na równym lub wyższym poziomie w hierarchii niż moja najwyższa rola. "
            "Przesuń rolę bota wyżej lub wybierz niższą rolę.",
            ephemeral=True
        )
        return

    try:
        database.update_server_config(guild_id=interaction.guild_id, verified_role_id=rola.id)
        await interaction.response.send_message(f"Rola dla zweryfikowanych członków została ustawiona na {rola.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd podczas ustawiania roli: {e}", ephemeral=True)

@set_verified_role_command.error
async def set_verified_role_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora, aby użyć tej komendy.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.tree.command(name="add_quiz_question", description="Dodaje pytanie do quizu weryfikacyjnego.")
@app_commands.describe(pytanie="Treść pytania.", odpowiedz="Poprawna odpowiedź na pytanie (wielkość liter ignorowana).")
@app_commands.checks.has_permissions(administrator=True)
async def add_quiz_question_command(interaction: discord.Interaction, pytanie: str, odpowiedz: str):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return
    try:
        question_id = database.add_quiz_question(interaction.guild_id, pytanie, odpowiedz.lower()) # Odpowiedzi przechowujemy małymi literami
        await interaction.response.send_message(f"Dodano pytanie do quizu (ID: {question_id}): \"{pytanie}\" z odpowiedzią \"{odpowiedz}\".", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Wystąpił błąd podczas dodawania pytania: {e}", ephemeral=True)

@add_quiz_question_command.error
async def add_quiz_question_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora, aby użyć tej komendy.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.tree.command(name="list_quiz_questions", description="Wyświetla listę pytań quizu weryfikacyjnego.")
@app_commands.checks.has_permissions(administrator=True)
async def list_quiz_questions_command(interaction: discord.Interaction):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    questions = database.get_quiz_questions(interaction.guild_id)
    if not questions:
        await interaction.response.send_message("Brak pytań w quizie dla tego serwera.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Pytania Quizu Weryfikacyjnego dla {interaction.guild.name}", color=discord.Color.orange())
    for q in questions:
        embed.add_field(name=f"ID: {q['id']} - Pytanie:", value=q['question'], inline=False)
        embed.add_field(name="Odpowiedź:", value=f"||{q['answer']}||", inline=False) # Odpowiedź w spoilerze
        if len(embed.fields) >= 24 and q != questions[-1]: # Discord limit 25 fields, zostaw miejsce na ostatnie
             await interaction.followup.send(embed=embed, ephemeral=True) # Wyslij obecny embed i zacznij nowy
             embed = discord.Embed(title=f"Pytania Quizu (cd.)", color=discord.Color.orange())

    if len(embed.fields) > 0 : # Jeśli coś zostało w ostatnim embedzie
        await interaction.response.send_message(embed=embed, ephemeral=True) if not interaction.response.is_done() else await interaction.followup.send(embed=embed,ephemeral=True)
    elif not interaction.response.is_done(): # Jeśli nie było żadnych pól, ale interakcja nie jest zakończona
        await interaction.response.send_message("Brak pytań do wyświetlenia (pusty embed).", ephemeral=True)


@list_quiz_questions_command.error
async def list_quiz_questions_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora, aby użyć tej komendy.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)


@bot.tree.command(name="remove_quiz_question", description="Usuwa pytanie z quizu weryfikacyjnego.")
@app_commands.describe(id_pytania="ID pytania, które chcesz usunąć (znajdziesz je komendą /list_quiz_questions).")
@app_commands.checks.has_permissions(administrator=True)
async def remove_quiz_question_command(interaction: discord.Interaction, id_pytania: int):
    if not interaction.guild_id:
        await interaction.response.send_message("Ta komenda może być użyta tylko na serwerze.", ephemeral=True)
        return

    if database.remove_quiz_question(id_pytania):
        await interaction.response.send_message(f"Pytanie o ID {id_pytania} zostało usunięte z quizu.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Nie znaleziono pytania o ID {id_pytania} w quizie dla tego serwera.", ephemeral=True)

@remove_quiz_question_command.error
async def remove_quiz_question_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień administratora, aby użyć tej komendy.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Wystąpił błąd: {error}", ephemeral=True)
