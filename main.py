import discord
from discord import app_commands # Import dla komend aplikacyjnych
from discord.ext import commands # Możemy użyć Bot zamiast Client dla lepszej obsługi komend
import os
from dotenv import load_dotenv
import database # Import naszego modułu bazy danych

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

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
    # await bot.process_commands(message) # Odkomentuj, jeśli używasz komend tekstowych z prefixem
