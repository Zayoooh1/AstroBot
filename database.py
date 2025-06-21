import sqlite3

DB_NAME = 'bot_config.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS server_configs (
        guild_id INTEGER PRIMARY KEY,
        welcome_message_content TEXT,
        reaction_role_id INTEGER,
        reaction_message_id INTEGER
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS timed_roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        expiration_timestamp INTEGER NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_activity (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        message_count INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_role_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        required_message_count INTEGER NOT NULL,
        UNIQUE (guild_id, role_id),
        UNIQUE (guild_id, required_message_count)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quiz_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS banned_words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        word TEXT NOT NULL,
        UNIQUE (guild_id, word)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS punishments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('mute', 'ban', 'kick', 'warn')),
        reason TEXT,
        expires_at INTEGER,
        active BOOLEAN DEFAULT TRUE,
        created_at INTEGER NOT NULL
    )
    """)
    # Indeksy dla częstych zapytań
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_punishments_user_guild ON punishments (user_id, guild_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_punishments_expires_active ON punishments (expires_at, active)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS level_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        level INTEGER NOT NULL,
        role_id_to_grant INTEGER,
        custom_message_on_level_up TEXT,
        UNIQUE (guild_id, level, role_id_to_grant)
    )
    """)
    # Indeks dla szybkiego wyszukiwania nagród dla poziomu
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_level_rewards_guild_level ON level_rewards (guild_id, level)")

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print(f"Baza danych '{DB_NAME}' zainicjalizowana z tabelami 'server_configs', 'timed_roles', 'user_activity', 'activity_role_configs', 'quiz_questions', 'banned_words', 'punishments' i 'level_rewards'.")

def update_server_config(guild_id: int, welcome_message_content: str = None,
                         reaction_role_id: int = None, reaction_message_id: int = None,
                         unverified_role_id: int = None, verified_role_id: int = None,
                         moderation_log_channel_id: int = None, # Dla logów z auto-moderacji
                         filter_profanity_enabled: bool = None,
                         filter_spam_enabled: bool = None,
                         filter_invites_enabled: bool = None,
                         muted_role_id: int = None,
                         moderator_actions_log_channel_id: int = None
                         ):
    import time # Potrzebny dla created_at w punishments, ale też ogólnie może być przydatny
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Ensure the server_configs row exists
    cursor.execute("INSERT OR IGNORE INTO server_configs (guild_id) VALUES (?)", (guild_id,))

    updates = []
    params = []

    if welcome_message_content is not None:
        updates.append("welcome_message_content = ?")
        params.append(welcome_message_content)
    if reaction_role_id is not None:
        updates.append("reaction_role_id = ?")
        params.append(reaction_role_id)
    if reaction_message_id is not None:
        updates.append("reaction_message_id = ?")
        params.append(reaction_message_id)
    if unverified_role_id is not None:
        updates.append("unverified_role_id = ?")
        params.append(unverified_role_id)
    if verified_role_id is not None:
        updates.append("verified_role_id = ?")
        params.append(verified_role_id)
    if moderation_log_channel_id is not None:
        updates.append("moderation_log_channel_id = ?")
        params.append(moderation_log_channel_id)
    if filter_profanity_enabled is not None:
        updates.append("filter_profanity_enabled = ?")
        params.append(filter_profanity_enabled)
    if filter_spam_enabled is not None:
        updates.append("filter_spam_enabled = ?")
        params.append(filter_spam_enabled)
    if filter_invites_enabled is not None:
        updates.append("filter_invites_enabled = ?")
        params.append(filter_invites_enabled)
    if muted_role_id is not None:
        updates.append("muted_role_id = ?")
        params.append(muted_role_id)
    if moderator_actions_log_channel_id is not None:
        updates.append("moderator_actions_log_channel_id = ?")
        params.append(moderator_actions_log_channel_id)

    if updates:
        sql = f"UPDATE server_configs SET {', '.join(updates)} WHERE guild_id = ?"
        params.append(guild_id)
        cursor.execute(sql, tuple(params))

    conn.commit()
    conn.close()

def get_server_config(guild_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT welcome_message_content, reaction_role_id, reaction_message_id,
               unverified_role_id, verified_role_id,
               moderation_log_channel_id, filter_profanity_enabled,
               filter_spam_enabled, filter_invites_enabled,
               muted_role_id, moderator_actions_log_channel_id
        FROM server_configs
        WHERE guild_id = ?
        """, (guild_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        # Konwersja wartości bool z bazy (0/1) i obsługa None dla nowo dodanych kolumn
        def get_bool(val, default=True):
            if val is None: return default
            return bool(val)

        return {
            "welcome_message_content": row[0],
            "reaction_role_id": row[1],
            "reaction_message_id": row[2],
            "unverified_role_id": row[3],
            "verified_role_id": row[4],
            "moderation_log_channel_id": row[5], # Dla auto-moderacji
            "filter_profanity_enabled": get_bool(row[6]),
            "filter_spam_enabled": get_bool(row[7]),
            "filter_invites_enabled": get_bool(row[8]),
            "muted_role_id": row[9], # Dla systemu kar
            "moderator_actions_log_channel_id": row[10] # Dla logów akcji moderatorów
        }
    return None


# --- Funkcje dla Systemu Kar (Punishments) ---

def add_punishment(guild_id: int, user_id: int, moderator_id: int,
                   punishment_type: str, reason: str | None, expires_at: int | None = None) -> int:
    import time
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    created_at = int(time.time())
    cursor.execute("""
    INSERT INTO punishments (guild_id, user_id, moderator_id, type, reason, expires_at, active, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (guild_id, user_id, moderator_id, punishment_type, reason, expires_at, True, created_at))
    punishment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return punishment_id

def deactivate_punishment(punishment_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE punishments SET active = FALSE WHERE id = ?", (punishment_id,))
    conn.commit()
    conn.close()

def get_active_user_punishment(guild_id: int, user_id: int, punishment_type: str) -> dict | None:
    """Sprawdza, czy użytkownik ma aktywną karę danego typu."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, moderator_id, reason, expires_at, created_at
    FROM punishments
    WHERE guild_id = ? AND user_id = ? AND type = ? AND active = TRUE
    ORDER BY created_at DESC LIMIT 1
    """, (guild_id, user_id, punishment_type)) # Weź najnowszą aktywną karę
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "moderator_id": row[1], "reason": row[2], "expires_at": row[3], "created_at": row[4]}
    return None

def get_expired_active_punishments(current_timestamp: int) -> list[dict]:
    """Pobiera aktywne kary (mute, ban), które już wygasły."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, guild_id, user_id, role_id, type, expires_at -- 'role_id' tu nie pasuje, to ogólna tabela kar
    FROM punishments                                        -- usunę 'role_id' z selecta
    WHERE active = TRUE AND expires_at IS NOT NULL AND expires_at <= ? AND type IN ('mute', 'ban')
    """, (current_timestamp,))
    # Poprawiony SELECT:
    cursor.execute("""
    SELECT id, guild_id, user_id, type, expires_at
    FROM punishments
    WHERE active = TRUE AND expires_at IS NOT NULL AND expires_at <= ? AND type IN ('mute', 'ban')
    """, (current_timestamp,))
    expired = [{"id": row[0], "guild_id": row[1], "user_id": row[2], "type": row[3], "expires_at": row[4]} for row in cursor.fetchall()]
    conn.close()
    return expired

def get_user_punishments(guild_id: int, user_id: int) -> list[dict]:
    """Pobiera wszystkie przypadki moderacyjne dla danego użytkownika na serwerze, posortowane od najnowszego."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, moderator_id, type, reason, expires_at, active, created_at
    FROM punishments
    WHERE guild_id = ? AND user_id = ?
    ORDER BY created_at DESC
    """, (guild_id, user_id))

    cases = []
    for row in cursor.fetchall():
        cases.append({
            "id": row[0],
            "moderator_id": row[1],
            "type": row[2],
            "reason": row[3],
            "expires_at": row[4],
            "active": bool(row[5]),
            "created_at": row[6]
        })
    conn.close()
    return cases


# --- Funkcje dla Czarnej Listy Słów (Moderacja) ---

# --- Funkcje dla Nagród za Poziomy (Level Rewards) ---

def add_level_reward(guild_id: int, level: int, role_id: int = None, message: str = None) -> int | None:
    """Dodaje nagrodę za poziom. Przynajmniej rola lub wiadomość musi być podana."""
    if role_id is None and message is None:
        return None # Nie można dodać pustej nagrody

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO level_rewards (guild_id, level, role_id_to_grant, custom_message_on_level_up)
        VALUES (?, ?, ?, ?)
        """, (guild_id, level, role_id, message))
        reward_id = cursor.lastrowid
        conn.commit()
        return reward_id
    except sqlite3.IntegrityError: # Naruszenie UNIQUE constraint
        conn.rollback()
        return None # Lub rzucić specyficzny błąd, np. RewardAlreadyExistsError
    finally:
        conn.close()

def remove_level_reward(reward_id: int) -> bool:
    """Usuwa nagrodę za poziom po jej ID. Zwraca True jeśli usunięto."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM level_rewards WHERE id = ?", (reward_id,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def get_rewards_for_level(guild_id: int, level: int) -> list[dict]:
    """Pobiera wszystkie nagrody skonfigurowane dla danego poziomu na serwerze."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, role_id_to_grant, custom_message_on_level_up
    FROM level_rewards
    WHERE guild_id = ? AND level = ?
    """, (guild_id, level))
    rewards = [
        {"id": row[0], "role_id_to_grant": row[1], "custom_message_on_level_up": row[2]}
        for row in cursor.fetchall()
    ]
    conn.close()
    return rewards

def get_all_level_rewards_config(guild_id: int) -> list[dict]:
    """Pobiera wszystkie skonfigurowane nagrody za poziomy dla serwera, posortowane po poziomie."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, level, role_id_to_grant, custom_message_on_level_up
    FROM level_rewards
    WHERE guild_id = ?
    ORDER BY level ASC
    """, (guild_id,))
    configs = [
        {"id": row[0], "level": row[1], "role_id_to_grant": row[2], "custom_message_on_level_up": row[3]}
        for row in cursor.fetchall()
    ]
    conn.close()
    return configs

# --- Funkcje dla Rankingu ---

def get_server_leaderboard(guild_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
    """Pobiera listę użytkowników do leaderboardu, posortowaną po XP."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT user_id, xp, level
    FROM user_activity
    WHERE guild_id = ? AND xp > 0 -- Tylko użytkownicy z jakimkolwiek XP
    ORDER BY xp DESC, level DESC
    LIMIT ? OFFSET ?
    """, (guild_id, limit, offset))
    leaderboard = [
        {"user_id": row[0], "xp": row[1], "level": row[2]}
        for row in cursor.fetchall()
    ]
    conn.close()
    return leaderboard

def get_user_rank_in_server(guild_id: int, user_id: int) -> tuple[int, int] | None:
    """Zwraca pozycję użytkownika w rankingu serwera i całkowitą liczbę graczy w rankingu.
       Zwraca None, jeśli użytkownik nie ma XP."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Najpierw sprawdź, czy użytkownik ma jakiekolwiek XP
    cursor.execute("SELECT xp FROM user_activity WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    user_xp_row = cursor.fetchone()
    if not user_xp_row or user_xp_row[0] == 0:
        conn.close()
        return None # Użytkownik nie jest w rankingu

    # Pobierz wszystkich użytkowników z XP > 0, posortowanych
    cursor.execute("""
    SELECT user_id FROM user_activity
    WHERE guild_id = ? AND xp > 0
    ORDER BY xp DESC, level DESC, user_id ASC -- user_id dla stabilnego sortowania przy remisach XP/level
    """, (guild_id,))

    ranked_users = [row[0] for row in cursor.fetchall()]
    total_ranked_players = len(ranked_users)

    try:
        rank = ranked_users.index(user_id) + 1
        conn.close()
        return rank, total_ranked_players
    except ValueError: # Użytkownik nie znaleziony na liście (nie powinien się zdarzyć, jeśli ma XP)
        conn.close()
        return None


def add_banned_word(guild_id: int, word: str) -> bool:
    """Dodaje słowo do czarnej listy. Zwraca True jeśli dodano, False jeśli już istnieje."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO banned_words (guild_id, word) VALUES (?, ?)", (guild_id, word.lower()))
        conn.commit()
        return True
    except sqlite3.IntegrityError: # Słowo już istnieje dla tego guild_id
        return False
    finally:
        conn.close()

def remove_banned_word(guild_id: int, word: str) -> bool:
    """Usuwa słowo z czarnej listy. Zwraca True jeśli usunięto, False jeśli nie znaleziono."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM banned_words WHERE guild_id = ? AND word = ?", (guild_id, word.lower()))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def get_banned_words(guild_id: int) -> list[str]:
    """Pobiera listę zakazanych słów dla danego serwera."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT word FROM banned_words WHERE guild_id = ?", (guild_id,))
    words = [row[0] for row in cursor.fetchall()]
    conn.close()
    return words

# --- Funkcje dla Quizu Weryfikacyjnego ---

def add_quiz_question(guild_id: int, question: str, answer: str) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO quiz_questions (guild_id, question, answer)
    VALUES (?, ?, ?)
    """, (guild_id, question, answer))
    question_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return question_id

def remove_quiz_question(question_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM quiz_questions WHERE id = ?", (question_id,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def get_quiz_questions(guild_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, question, answer FROM quiz_questions WHERE guild_id = ?", (guild_id,))
    questions = [{"id": row[0], "question": row[1], "answer": row[2]} for row in cursor.fetchall()]
    conn.close()
    return questions

# Funkcje CRUD dla timed_roles

def add_timed_role(guild_id: int, user_id: int, role_id: int, expiration_timestamp: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO timed_roles (guild_id, user_id, role_id, expiration_timestamp)
    VALUES (?, ?, ?, ?)
    """, (guild_id, user_id, role_id, expiration_timestamp))
    conn.commit()
    conn.close()

def get_expired_roles(current_timestamp: int) -> list[tuple[int, int, int, int, int]]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, guild_id, user_id, role_id, expiration_timestamp FROM timed_roles
    WHERE expiration_timestamp <= ?
    """, (current_timestamp,))
    expired_roles = cursor.fetchall()
    conn.close()
    return expired_roles

def remove_timed_role(timed_role_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM timed_roles WHERE id = ?", (timed_role_id,))
    conn.commit()
    conn.close()

def get_active_timed_role(guild_id: int, user_id: int, role_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, expiration_timestamp FROM timed_roles
    WHERE guild_id = ? AND user_id = ? AND role_id = ? AND expiration_timestamp > strftime('%s', 'now')
    """, (guild_id, user_id, role_id)) # strftime('%s', 'now') to aktualny unix timestamp
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "expiration_timestamp": row[1]}
    return None

# --- Funkcje dla Aktywności Użytkownika (Wiadomości, XP, Poziomy) ---

def ensure_user_activity_entry(guild_id: int, user_id: int):
    """Upewnia się, że wpis dla użytkownika istnieje, tworząc go jeśli nie."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR IGNORE INTO user_activity (guild_id, user_id, message_count, xp, level)
    VALUES (?, ?, 0, 0, 0)
    """, (guild_id, user_id))
    conn.commit()
    conn.close()

def increment_message_count(guild_id: int, user_id: int):
    ensure_user_activity_entry(guild_id, user_id)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE user_activity
    SET message_count = message_count + 1
    WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))
    conn.commit()
    conn.close()

def add_xp(guild_id: int, user_id: int, xp_amount: int) -> int:
    ensure_user_activity_entry(guild_id, user_id)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE user_activity
    SET xp = xp + ?
    WHERE guild_id = ? AND user_id = ?
    """, (xp_amount, guild_id, user_id))
    conn.commit()

    cursor.execute("SELECT xp FROM user_activity WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    new_total_xp = cursor.fetchone()[0]
    conn.close()
    return new_total_xp

def get_user_stats(guild_id: int, user_id: int) -> dict:
    ensure_user_activity_entry(guild_id, user_id) # Upewnij się, że użytkownik ma wpis
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT message_count, xp, level FROM user_activity WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"message_count": row[0], "xp": row[1], "level": row[2]}
    return {"message_count": 0, "xp": 0, "level": 0} # Powinno być utworzone przez ensure

def set_user_level(guild_id: int, user_id: int, new_level: int):
    ensure_user_activity_entry(guild_id, user_id)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE user_activity
    SET level = ?
    WHERE guild_id = ? AND user_id = ?
    """, (new_level, guild_id, user_id))
    conn.commit()
    conn.close()

# (Opcjonalnie) Funkcja do jednoczesnego ustawiania poziomu i XP, jeśli potrzebna później
# def set_user_level_xp(guild_id: int, user_id: int, new_level: int, new_xp: int):
#     ensure_user_activity_entry(guild_id, user_id)
#     conn = sqlite3.connect(DB_NAME)
#     cursor = conn.cursor()
#     cursor.execute("""
#     UPDATE user_activity
#     SET level = ?, xp = ?
#     WHERE guild_id = ? AND user_id = ?
#     """, (new_level, new_xp, guild_id, user_id))
#     conn.commit()
#     conn.close()


# --- Funkcje dla Konfiguracji Ról za Aktywność (pozostają bez zmian) ---
def add_activity_role_config(guild_id: int, role_id: int, required_message_count: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO activity_role_configs (guild_id, role_id, required_message_count)
        VALUES (?, ?, ?)
        """, (guild_id, role_id, required_message_count))
        conn.commit()
    except sqlite3.IntegrityError as e:
        # Złapanie błędu unikalności (np. rola już skonfigurowana, lub próg już istnieje dla tego serwera)
        conn.rollback()
        raise e # Przekaż błąd dalej, aby obsłużyć go w komendzie
    finally:
        conn.close()

def remove_activity_role_config(guild_id: int, role_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM activity_role_configs WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
    conn.commit()
    deleted_rows = cursor.rowcount
    conn.close()
    return deleted_rows > 0


def get_activity_role_configs(guild_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT role_id, required_message_count FROM activity_role_configs
    WHERE guild_id = ? ORDER BY required_message_count ASC
    """, (guild_id,)) # Sortuj ASC, aby łatwiej znaleźć najwyższą kwalifikującą
    configs = [{"role_id": row[0], "required_message_count": row[1]} for row in cursor.fetchall()]
    conn.close()
    return configs

def get_highest_eligible_role(guild_id: int, current_message_count: int) -> dict | None:
    """Znajduje najwyższą (pod względem liczby wiadomości) rolę, na którą kwalifikuje się użytkownik."""
    configs = get_activity_role_configs(guild_id) # Te są posortowane ASC
    eligible_role = None
    for config in configs:
        if current_message_count >= config["required_message_count"]:
            eligible_role = config # Nadpisuj, bo chcemy najwyższy próg, który spełniamy
        else:
            break # Jeśli nie spełniamy tego progu, nie spełnimy też wyższych (bo są ASC)
    return eligible_role
