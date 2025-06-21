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
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print(f"Baza danych '{DB_NAME}' zainicjalizowana z tabelami 'server_configs', 'timed_roles', 'user_activity' i 'activity_role_configs'.")

def update_server_config(guild_id: int, welcome_message_content: str = None, reaction_role_id: int = None, reaction_message_id: int = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO server_configs (guild_id) VALUES (?)", (guild_id,))
    if welcome_message_content is not None:
        cursor.execute("UPDATE server_configs SET welcome_message_content = ? WHERE guild_id = ?", (welcome_message_content, guild_id))
    if reaction_role_id is not None:
        cursor.execute("UPDATE server_configs SET reaction_role_id = ? WHERE guild_id = ?", (reaction_role_id, guild_id))
    if reaction_message_id is not None:
        cursor.execute("UPDATE server_configs SET reaction_message_id = ? WHERE guild_id = ?", (reaction_message_id, guild_id))
    conn.commit()
    conn.close()

def get_server_config(guild_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT welcome_message_content, reaction_role_id, reaction_message_id FROM server_configs WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"welcome_message_content": row[0], "reaction_role_id": row[1], "reaction_message_id": row[2]}
    return None

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

# --- Funkcje dla Ról za Aktywność ---

def increment_message_count(guild_id: int, user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO user_activity (guild_id, user_id, message_count)
    VALUES (?, ?, 1)
    ON CONFLICT(guild_id, user_id) DO UPDATE SET message_count = message_count + 1
    """, (guild_id, user_id))
    conn.commit()
    conn.close()

def get_message_count(guild_id: int, user_id: int) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT message_count FROM user_activity WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

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
