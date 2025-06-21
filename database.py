import sqlite3
import time
import json # Dodano import json

DB_NAME = 'bot_config.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS server_configs (
        guild_id INTEGER PRIMARY KEY,
        welcome_message_content TEXT,
        reaction_role_id INTEGER,
        reaction_message_id INTEGER,
        unverified_role_id INTEGER,
        verified_role_id INTEGER,
        moderation_log_channel_id INTEGER,
        filter_profanity_enabled BOOLEAN DEFAULT TRUE,
        filter_spam_enabled BOOLEAN DEFAULT TRUE,
        filter_invites_enabled BOOLEAN DEFAULT TRUE,
        muted_role_id INTEGER,
        moderator_actions_log_channel_id INTEGER
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_level_rewards_guild_level ON level_rewards (guild_id, level)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER UNIQUE,
        question TEXT NOT NULL,
        created_by_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        ends_at INTEGER,
        is_active BOOLEAN DEFAULT TRUE,
        results_message_id INTEGER
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_polls_guild_active_ends ON polls (guild_id, is_active, ends_at)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS poll_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id INTEGER NOT NULL,
        option_text TEXT NOT NULL,
        reaction_emoji TEXT NOT NULL,
        FOREIGN KEY(poll_id) REFERENCES polls(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poll_options_poll_id ON poll_options (poll_id)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER UNIQUE,
        prize TEXT NOT NULL,
        winner_count INTEGER DEFAULT 1,
        created_by_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        ends_at INTEGER NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        required_role_id INTEGER,
        min_level INTEGER,
        winners_json TEXT
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_giveaways_guild_active_ends ON giveaways (guild_id, is_active, ends_at)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS custom_commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        command_name TEXT NOT NULL,
        response_type TEXT NOT NULL CHECK(response_type IN ('text', 'embed')),
        response_content TEXT NOT NULL,
        created_by_id INTEGER,
        created_at INTEGER,
        last_edited_by_id INTEGER,
        last_edited_at INTEGER,
        UNIQUE (guild_id, command_name)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_custom_commands_guild_name ON custom_commands (guild_id, command_name)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER UNIQUE,
        user_id INTEGER NOT NULL,
        topic TEXT,
        created_at INTEGER NOT NULL,
        is_open BOOLEAN DEFAULT TRUE,
        closed_by_id INTEGER,
        closed_at INTEGER
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_guild_user_open ON tickets (guild_id, user_id, is_open)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_channel_id ON tickets (channel_id)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tracked_creators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        platform TEXT NOT NULL CHECK(platform IN ('twitch', 'youtube')),
        creator_identifier TEXT NOT NULL, -- Nazwa kanału Twitch, ID kanału YouTube
        discord_channel_id INTEGER NOT NULL,
        custom_notification_message TEXT,
        last_notified_id TEXT,            -- ID ostatniego streama/video
        last_checked_at INTEGER,
        UNIQUE (guild_id, platform, creator_identifier, discord_channel_id)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracked_creators_guild_platform ON tracked_creators (guild_id, platform)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS watched_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER, -- Może być NULL jeśli produkt jest globalny dla bota, lub ID serwera jeśli per-serwer
        user_id_who_added INTEGER NOT NULL,
        product_url TEXT NOT NULL UNIQUE,
        shop_name TEXT NOT NULL,
        product_name TEXT,
        last_known_price_str TEXT,
        last_known_availability_str TEXT,
        last_scanned_at INTEGER,
        is_active BOOLEAN DEFAULT TRUE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_watched_products_url ON watched_products (product_url)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_watched_products_active_shop ON watched_products (is_active, shop_name)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watched_product_id INTEGER NOT NULL,
        scan_date INTEGER NOT NULL,
        price_str TEXT,
        availability_str TEXT,
        FOREIGN KEY(watched_product_id) REFERENCES watched_products(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_product_date ON price_history (watched_product_id, scan_date DESC)")

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print(f"Baza danych '{DB_NAME}' zainicjalizowana z tabelami 'server_configs', 'timed_roles', 'user_activity', 'activity_role_configs', 'quiz_questions', 'banned_words', 'punishments', 'level_rewards', 'polls', 'poll_options', 'giveaways', 'custom_commands', 'tickets', 'tracked_creators', 'watched_products' i 'price_history'.")

def update_server_config(guild_id: int, welcome_message_content: str = None,
                         reaction_role_id: int = None, reaction_message_id: int = None,
                         unverified_role_id: int = None, verified_role_id: int = None,
                         moderation_log_channel_id: int = None,
                         filter_profanity_enabled: bool = None,
                         filter_spam_enabled: bool = None,
                         filter_invites_enabled: bool = None,
                         muted_role_id: int = None,
                         moderator_actions_log_channel_id: int = None,
                         custom_command_prefix: str = None,
                         ticket_category_id: int = None,
                         ticket_log_channel_id: int = None,
                         ticket_support_role_ids_json: str = None, # Przechowujemy jako JSON string
                         feedback_channel_id: int = None
                         ):
    import json # Potrzebne do serializacji/deserializacji listy ID ról
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO server_configs (guild_id) VALUES (?)", (guild_id,))

    updates = []
    params = []

    def add_update(field_name, value):
        if value is not None:
            updates.append(f"{field_name} = ?")
            params.append(value)

    add_update("welcome_message_content", welcome_message_content)
    add_update("reaction_role_id", reaction_role_id)
    add_update("reaction_message_id", reaction_message_id)
    add_update("unverified_role_id", unverified_role_id)
    add_update("verified_role_id", verified_role_id)
    add_update("moderation_log_channel_id", moderation_log_channel_id)
    add_update("filter_profanity_enabled", filter_profanity_enabled)
    add_update("filter_spam_enabled", filter_spam_enabled)
    add_update("filter_invites_enabled", filter_invites_enabled)
    add_update("muted_role_id", muted_role_id)
    add_update("moderator_actions_log_channel_id", moderator_actions_log_channel_id)
    add_update("custom_command_prefix", custom_command_prefix)
    add_update("ticket_category_id", ticket_category_id)
    add_update("ticket_log_channel_id", ticket_log_channel_id)
    add_update("ticket_support_role_ids_json", ticket_support_role_ids_json)
    add_update("feedback_channel_id", feedback_channel_id)

    if updates:
        sql = f"UPDATE server_configs SET {', '.join(updates)} WHERE guild_id = ?"
        params.append(guild_id)
        cursor.execute(sql, tuple(params))

    conn.commit()
    conn.close()

def get_server_config(guild_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(server_configs)")
    available_columns = [row[1] for row in cursor.fetchall()]

    all_config_keys = {
        "welcome_message_content": None, "reaction_role_id": None, "reaction_message_id": None,
        "unverified_role_id": None, "verified_role_id": None,
        "moderation_log_channel_id": None,
        "filter_profanity_enabled": True, "filter_spam_enabled": True, "filter_invites_enabled": True,
        "muted_role_id": None, "moderator_actions_log_channel_id": None,
        "custom_command_prefix": "!",
        "ticket_category_id": None, "ticket_log_channel_id": None, "ticket_support_role_ids_json": "[]",
        "feedback_channel_id": None # Domyślnie None
    }

    select_cols_str = ", ".join([key for key in all_config_keys if key in available_columns])
    if not select_cols_str:
        conn.close()
        cursor.execute(f"SELECT guild_id FROM server_configs WHERE guild_id = ?", (guild_id,))
        if not cursor.fetchone():
            conn.close()
            return None
        # Jeśli wiersz istnieje, ale nie ma żadnych pasujących kolumn (bardzo mało prawdopodobne)
        return all_config_keys


    cursor.execute(f"SELECT {select_cols_str} FROM server_configs WHERE guild_id = ?", (guild_id,))
    row_values = cursor.fetchone()

    if not row_values: # Nie ma wpisu dla tego guild_id
        conn.close()
        return None

    config_result = all_config_keys.copy()
    fetched_data = dict(zip([key for key in all_config_keys if key in available_columns], row_values))
    for key, value in fetched_data.items():
        if key in ["filter_profanity_enabled", "filter_spam_enabled", "filter_invites_enabled"]:
            config_result[key] = bool(value) if value is not None else all_config_keys[key]
        else:
            config_result[key] = value if value is not None else all_config_keys[key]
    conn.close()
    return config_result


# --- Funkcje dla Systemu Kar (Punishments) ---
def add_punishment(guild_id: int, user_id: int, moderator_id: int,
                   punishment_type: str, reason: str | None, expires_at: int | None = None) -> int:
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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, moderator_id, reason, expires_at, created_at
    FROM punishments
    WHERE guild_id = ? AND user_id = ? AND type = ? AND active = TRUE
    ORDER BY created_at DESC LIMIT 1
    """, (guild_id, user_id, punishment_type))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "moderator_id": row[1], "reason": row[2], "expires_at": row[3], "created_at": row[4]}
    return None

def get_expired_active_punishments(current_timestamp: int) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, guild_id, user_id, type, expires_at
    FROM punishments
    WHERE active = TRUE AND expires_at IS NOT NULL AND expires_at <= ? AND type IN ('mute', 'ban')
    """, (current_timestamp,))
    expired = [{"id": row[0], "guild_id": row[1], "user_id": row[2], "type": row[3], "expires_at": row[4]} for row in cursor.fetchall()]
    conn.close()
    return expired

def get_user_punishments(guild_id: int, user_id: int) -> list[dict]:
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
def add_banned_word(guild_id: int, word: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO banned_words (guild_id, word) VALUES (?, ?)", (guild_id, word.lower()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_banned_word(guild_id: int, word: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM banned_words WHERE guild_id = ? AND word = ?", (guild_id, word.lower()))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def get_banned_words(guild_id: int) -> list[str]:
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

# --- Funkcje dla Ról Czasowych (Timed Roles) ---
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
    """, (guild_id, user_id, role_id))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "expiration_timestamp": row[1]}
    return None

# --- Funkcje dla Aktywności Użytkownika (Wiadomości, XP, Poziomy) ---
def ensure_user_activity_entry(guild_id: int, user_id: int):
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
    ensure_user_activity_entry(guild_id, user_id)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT message_count, xp, level FROM user_activity WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"message_count": row[0], "xp": row[1], "level": row[2]}
    return {"message_count": 0, "xp": 0, "level": 0}

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

# --- Funkcje dla Konfiguracji Ról za Aktywność ---
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
        conn.rollback()
        raise e
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
    """, (guild_id,))
    configs = [{"role_id": row[0], "required_message_count": row[1]} for row in cursor.fetchall()]
    conn.close()
    return configs

def get_highest_eligible_role(guild_id: int, current_message_count: int) -> dict | None:
    configs = get_activity_role_configs(guild_id)
    eligible_role = None
    for config in configs:
        if current_message_count >= config["required_message_count"]:
            eligible_role = config
        else:
            break
    return eligible_role

# --- Funkcje dla Nagród za Poziomy (Level Rewards) ---
def add_level_reward(guild_id: int, level: int, role_id: int = None, message: str = None) -> int | None:
    if role_id is None and message is None:
        return None
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
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()

def remove_level_reward(reward_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM level_rewards WHERE id = ?", (reward_id,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def get_rewards_for_level(guild_id: int, level: int) -> list[dict]:
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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT user_id, xp, level
    FROM user_activity
    WHERE guild_id = ? AND xp > 0
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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT xp FROM user_activity WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    user_xp_row = cursor.fetchone()
    if not user_xp_row or user_xp_row[0] == 0:
        conn.close()
        return None

    cursor.execute("""
    SELECT user_id FROM user_activity
    WHERE guild_id = ? AND xp > 0
    ORDER BY xp DESC, level DESC, user_id ASC
    """, (guild_id,))

    ranked_users = [row[0] for row in cursor.fetchall()]
    total_ranked_players = len(ranked_users)

    try:
        rank = ranked_users.index(user_id) + 1
        conn.close()
        return rank, total_ranked_players
    except ValueError:
        conn.close()
        return None

# --- Funkcje dla Monitorowania Produktów (Product Watchlist) ---

def add_watched_product(user_id: int, url: str, shop_name: str, guild_id: int = None) -> int | None:
    """Dodaje nowy produkt do śledzenia. Zwraca ID produktu lub None jeśli już istnieje."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO watched_products (guild_id, user_id_who_added, product_url, shop_name, last_scanned_at)
        VALUES (?, ?, ?, ?, ?)
        """, (guild_id, user_id, url, shop_name.lower(), int(time.time())))
        product_id = cursor.lastrowid
        conn.commit()
        return product_id
    except sqlite3.IntegrityError: # product_url jest UNIQUE
        conn.rollback()
        # Można by tu pobrać ID istniejącego produktu, jeśli to potrzebne
        cursor.execute("SELECT id FROM watched_products WHERE product_url = ?", (url,))
        existing = cursor.fetchone()
        if existing: return existing[0] # Zwróć ID istniejącego, jeśli go znaleziono
        return None
    finally:
        conn.close()

def get_watched_product_by_url(url: str) -> dict | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, guild_id, user_id_who_added, shop_name, product_name,
           last_known_price_str, last_known_availability_str, last_scanned_at, is_active
    FROM watched_products WHERE product_url = ?
    """, (url,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "guild_id": row[1], "user_id_who_added": row[2], "shop_name": row[3],
            "product_name": row[4], "last_known_price_str": row[5],
            "last_known_availability_str": row[6], "last_scanned_at": row[7], "is_active": bool(row[8])
        }
    return None

def get_all_active_watched_products() -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, guild_id, user_id_who_added, product_url, shop_name, product_name,
           last_known_price_str, last_known_availability_str, last_scanned_at
    FROM watched_products
    WHERE is_active = TRUE
    """)
    products = [
        {
            "id": row[0], "guild_id": row[1], "user_id_who_added": row[2], "product_url": row[3],
            "shop_name": row[4], "product_name": row[5], "last_known_price_str": row[6],
            "last_known_availability_str": row[7], "last_scanned_at": row[8]
        } for row in cursor.fetchall()
    ]
    conn.close()
    return products

def update_watched_product_data(product_id: int, name: str | None, price_str: str | None,
                                availability_str: str | None, scanned_at: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    updates = []
    params = []
    if name is not None: updates.append("product_name = ?"); params.append(name)
    if price_str is not None: updates.append("last_known_price_str = ?"); params.append(price_str)
    if availability_str is not None: updates.append("last_known_availability_str = ?"); params.append(availability_str)
    updates.append("last_scanned_at = ?"); params.append(scanned_at)

    if updates: # Powinno zawsze być, bo scanned_at jest wymagane
        sql = f"UPDATE watched_products SET {', '.join(updates)} WHERE id = ?"
        params.append(product_id)
        cursor.execute(sql, tuple(params))
        conn.commit()
    conn.close()

def add_price_history_entry(watched_product_id: int, scan_date: int, price_str: str | None, availability_str: str | None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO price_history (watched_product_id, scan_date, price_str, availability_str)
    VALUES (?, ?, ?, ?)
    """, (watched_product_id, scan_date, price_str, availability_str))
    conn.commit()
    conn.close()

def get_product_price_history(watched_product_id: int, limit: int = 10) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT scan_date, price_str, availability_str
    FROM price_history
    WHERE watched_product_id = ?
    ORDER BY scan_date DESC
    LIMIT ?
    """, (watched_product_id, limit))
    history = [
        {"scan_date": row[0], "price_str": row[1], "availability_str": row[2]}
        for row in cursor.fetchall()
    ]
    conn.close()
    return history

def deactivate_watched_product(product_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE watched_products SET is_active = FALSE WHERE id = ?", (product_id,))
    updated_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return updated_rows > 0

def get_user_watched_products(user_id: int, guild_id: int | None = None) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    sql = """
    SELECT id, product_url, shop_name, product_name, last_known_price_str, last_known_availability_str
    FROM watched_products
    WHERE user_id_who_added = ? AND is_active = TRUE
    """
    params = [user_id]
    if guild_id is not None: # Jeśli chcemy filtrować po serwerze
        sql += " AND guild_id = ?"
        params.append(guild_id)

    cursor.execute(sql, tuple(params))
    products = [
        {
            "id": row[0], "product_url": row[1], "shop_name": row[2], "product_name": row[3],
            "last_known_price_str": row[4], "last_known_availability_str": row[5]
        } for row in cursor.fetchall()
    ]
    conn.close()
    return products

# --- Funkcje dla Ankiet (Polls) ---
def create_poll(guild_id: int, channel_id: int, question: str, created_by_id: int, ends_at: int | None = None) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    created_at_ts = int(time.time())
    cursor.execute("""
    INSERT INTO polls (guild_id, channel_id, question, created_by_id, created_at, ends_at, is_active)
    VALUES (?, ?, ?, ?, ?, ?, TRUE)
    """, (guild_id, channel_id, question, created_by_id, created_at_ts, ends_at))
    poll_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return poll_id

def add_poll_option(poll_id: int, option_text: str, reaction_emoji: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO poll_options (poll_id, option_text, reaction_emoji)
    VALUES (?, ?, ?)
    """, (poll_id, option_text, reaction_emoji))
    conn.commit()
    conn.close()

def set_poll_message_id(poll_id: int, message_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE polls SET message_id = ? WHERE id = ?", (message_id, poll_id))
    conn.commit()
    conn.close()

def get_poll_by_message_id(message_id: int) -> dict | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, guild_id, channel_id, question, created_by_id, created_at, ends_at, is_active, results_message_id FROM polls WHERE message_id = ?", (message_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "guild_id": row[1], "channel_id": row[2], "question": row[3],
            "created_by_id": row[4], "created_at": row[5], "ends_at": row[6],
            "is_active": bool(row[7]), "results_message_id": row[8]
        }
    return None

def get_active_polls_to_close(current_timestamp: int) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, guild_id, channel_id, message_id, question, created_by_id
    FROM polls
    WHERE is_active = TRUE AND ends_at IS NOT NULL AND ends_at <= ?
    """, (current_timestamp,))
    polls_to_close = [
        {"id": row[0], "guild_id": row[1], "channel_id": row[2], "message_id": row[3], "question": row[4], "created_by_id": row[5]}
        for row in cursor.fetchall()
    ]
    conn.close()
    return polls_to_close

def close_poll(poll_id: int, results_message_id: int | None = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if results_message_id:
        cursor.execute("UPDATE polls SET is_active = FALSE, results_message_id = ? WHERE id = ?", (results_message_id, poll_id))
    else:
        cursor.execute("UPDATE polls SET is_active = FALSE WHERE id = ?", (poll_id,))
    conn.commit()
    conn.close()

def get_poll_options(poll_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, option_text, reaction_emoji FROM poll_options WHERE poll_id = ?", (poll_id,))
    options = [{"id": row[0], "option_text": row[1], "reaction_emoji": row[2]} for row in cursor.fetchall()]
    conn.close()
    return options

def get_poll_details(poll_id: int) -> dict | None:
    """Pobiera szczegóły ankiety wraz z jej opcjami."""
    poll_data = {}
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, guild_id, channel_id, message_id, question, created_by_id, created_at, ends_at, is_active, results_message_id FROM polls WHERE id = ?", (poll_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    poll_data = {
        "id": row[0], "guild_id": row[1], "channel_id": row[2], "message_id": row[3],
        "question": row[4], "created_by_id": row[5], "created_at": row[6], "ends_at": row[7],
        "is_active": bool(row[8]), "results_message_id": row[9]
    }
    poll_data["options"] = get_poll_options(poll_id) # Pobierz opcje dla tej ankiety
    conn.close()
    return poll_data

# --- Funkcje dla Niestandardowych Komend (Custom Commands) ---
def add_custom_command(guild_id: int, name: str, response_type: str, content: str, creator_id: int) -> int | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    created_at_ts = int(time.time())
    try:
        cursor.execute("""
        INSERT INTO custom_commands (guild_id, command_name, response_type, response_content, created_by_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (guild_id, name.lower(), response_type, content, creator_id, created_at_ts))
        command_id = cursor.lastrowid
        conn.commit()
        return command_id
    except sqlite3.IntegrityError: # Nazwa komendy już istnieje
        conn.rollback()
        return None
    finally:
        conn.close()

def edit_custom_command(guild_id: int, name: str, new_response_type: str, new_content: str, editor_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    last_edited_at_ts = int(time.time())
    cursor.execute("""
    UPDATE custom_commands
    SET response_type = ?, response_content = ?, last_edited_by_id = ?, last_edited_at = ?
    WHERE guild_id = ? AND command_name = ?
    """, (new_response_type, new_content, editor_id, last_edited_at_ts, guild_id, name.lower()))
    updated_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return updated_rows > 0

def remove_custom_command(guild_id: int, name: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM custom_commands WHERE guild_id = ? AND command_name = ?", (guild_id, name.lower()))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def get_custom_command(guild_id: int, name: str) -> dict | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, response_type, response_content, created_by_id, created_at, last_edited_by_id, last_edited_at
    FROM custom_commands
    WHERE guild_id = ? AND command_name = ?
    """, (guild_id, name.lower()))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "response_type": row[1], "response_content": row[2],
            "created_by_id": row[3], "created_at": row[4],
            "last_edited_by_id": row[5], "last_edited_at": row[6]
        }
    return None

def get_all_custom_commands(guild_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, command_name, response_type
    FROM custom_commands
    WHERE guild_id = ?
    ORDER BY command_name ASC
    """, (guild_id,))
    commands_list = [{"id": row[0], "command_name": row[1], "response_type": row[2]} for row in cursor.fetchall()]
    conn.close()
    return commands_list


# --- Funkcje dla Konkursów (Giveaways) ---
# import json # Już zaimportowany na górze

def create_giveaway(guild_id: int, channel_id: int, prize: str, winner_count: int,
                    created_by_id: int, ends_at: int,
                    required_role_id: int | None = None, min_level: int | None = None) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    created_at_ts = int(time.time())
    cursor.execute("""
    INSERT INTO giveaways (guild_id, channel_id, prize, winner_count, created_by_id, created_at, ends_at,
                           required_role_id, min_level, is_active, winners_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, NULL)
    """, (guild_id, channel_id, prize, winner_count, created_by_id, created_at_ts, ends_at,
          required_role_id, min_level))
    giveaway_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return giveaway_id

# --- Funkcje dla Ticketów ---
def create_ticket(guild_id: int, user_id: int, topic: str | None) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    created_at_ts = int(time.time())
    cursor.execute("""
    INSERT INTO tickets (guild_id, user_id, topic, created_at, is_open)
    VALUES (?, ?, ?, ?, TRUE)
    """, (guild_id, user_id, topic, created_at_ts))
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ticket_id

def set_ticket_channel_id(ticket_id: int, channel_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE tickets SET channel_id = ? WHERE id = ?", (channel_id, ticket_id))
    conn.commit()
    conn.close()

def get_open_ticket_by_user(guild_id: int, user_id: int) -> dict | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, channel_id, topic, created_at
    FROM tickets
    WHERE guild_id = ? AND user_id = ? AND is_open = TRUE
    """, (guild_id, user_id))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "channel_id": row[1], "topic": row[2], "created_at": row[3]}
    return None

def get_ticket_by_channel(guild_id: int, channel_id: int) -> dict | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, user_id, topic, created_at, is_open, closed_by_id, closed_at
    FROM tickets
    WHERE guild_id = ? AND channel_id = ?
    """, (guild_id, channel_id))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "user_id": row[1], "topic": row[2], "created_at": row[3],
            "is_open": bool(row[4]), "closed_by_id": row[5], "closed_at": row[6]
        }
    return None

def close_ticket(ticket_id: int, closed_by_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    closed_at_ts = int(time.time())
    cursor.execute("""
    UPDATE tickets
    SET is_open = FALSE, closed_by_id = ?, closed_at = ?
    WHERE id = ?
    """, (closed_by_id, closed_at_ts, ticket_id))
    conn.commit()
    conn.close()


def set_giveaway_message_id(giveaway_id: int, message_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE giveaways SET message_id = ? WHERE id = ?", (message_id, giveaway_id))
    conn.commit()
    conn.close()

def get_active_giveaways_to_end(current_timestamp: int) -> list[dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, guild_id, channel_id, message_id, prize, winner_count, created_by_id, ends_at,
           required_role_id, min_level
    FROM giveaways
    WHERE is_active = TRUE AND ends_at <= ?
    """, (current_timestamp,))
    giveaways = [
        {
            "id": row[0], "guild_id": row[1], "channel_id": row[2], "message_id": row[3],
            "prize": row[4], "winner_count": row[5], "created_by_id": row[6], "ends_at": row[7],
            "required_role_id": row[8], "min_level": row[9]
        } for row in cursor.fetchall()
    ]
    conn.close()
    return giveaways

def end_giveaway(giveaway_id: int, winners_ids: list[int]):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    winners_json_str = json.dumps(winners_ids)
    cursor.execute("UPDATE giveaways SET is_active = FALSE, winners_json = ? WHERE id = ?", (winners_json_str, giveaway_id))
    conn.commit()
    conn.close()

def get_giveaway_details(message_id: int) -> dict | None: # Może być też po giveaway_id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Zakładamy, że message_id jest unikalne dla aktywnych/ostatnich konkursów,
    # ale jeśli chcemy historię, lepiej po giveaway_id. Na razie po message_id.
    cursor.execute("""
    SELECT id, guild_id, channel_id, prize, winner_count, created_by_id, created_at, ends_at,
           is_active, required_role_id, min_level, winners_json
    FROM giveaways
    WHERE message_id = ?
    """, (message_id,)) # Można dodać ORDER BY created_at DESC LIMIT 1 jeśli message_id nie jest UNIQUE globalnie
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "guild_id": row[1], "channel_id": row[2], "prize": row[3],
            "winner_count": row[4], "created_by_id": row[5], "created_at": row[6], "ends_at": row[7],
            "is_active": bool(row[8]), "required_role_id": row[9], "min_level": row[10],
            "winners_json": json.loads(row[11]) if row[11] else [] # Zwróć pustą listę jeśli NULL
        }
    return None
