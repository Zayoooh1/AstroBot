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
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print(f"Baza danych '{DB_NAME}' zainicjalizowana z tabelami 'server_configs', 'timed_roles', 'user_activity', 'activity_role_configs', 'quiz_questions' i 'banned_words'.")

def update_server_config(guild_id: int, welcome_message_content: str = None,
                         reaction_role_id: int = None, reaction_message_id: int = None,
                         unverified_role_id: int = None, verified_role_id: int = None,
                         moderation_log_channel_id: int = None,
                         filter_profanity_enabled: bool = None,
                         filter_spam_enabled: bool = None,
                         filter_invites_enabled: bool = None):
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
               filter_spam_enabled, filter_invites_enabled
        FROM server_configs
        WHERE guild_id = ?
        """, (guild_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "welcome_message_content": row[0],
            "reaction_role_id": row[1],
            "reaction_message_id": row[2],
            "unverified_role_id": row[3],
            "verified_role_id": row[4],
            "moderation_log_channel_id": row[5],
            # SQLite przechowuje BOOLEAN jako INTEGER 0 lub 1
            "filter_profanity_enabled": bool(row[6]) if row[6] is not None else True, # Domyślnie True
            "filter_spam_enabled": bool(row[7]) if row[7] is not None else True,       # Domyślnie True
            "filter_invites_enabled": bool(row[8]) if row[8] is not None else True   # Domyślnie True
        }
    # Zwróć domyślną konfigurację, jeśli wiersz nie istnieje, ale upewnij się, że guild_id jest tam
    # Lepiej jest, gdy `update_server_config` tworzy wiersz, a ta funkcja zwraca None, jeśli go nie ma
    # lub podstawowe wartości domyślne, jeśli jest, ale niektóre pola są None.
    # Dla spójności, jeśli INSERT OR IGNORE w update_server_config tworzy wiersz, to pola będą NULL.
    # Tutaj nadajemy im wartości domyślne, jeśli są NULL w bazie.
    # Jeśli serwer nie ma w ogóle wpisu, zwracamy None.
    return None


# --- Funkcje dla Czarnej Listy Słów (Moderacja) ---

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
