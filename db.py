import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
from typing import List, Dict, Optional

# Load environment variables
load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

def is_user_allowed(user_id: int) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM allowed_users WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result is not None
    except Error as e:
        print(f"DB error in is_user_allowed: {e}")
        return False

def add_user(user_id: int, username: Optional[str]) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('REPLACE INTO allowed_users (user_id, username) VALUES (%s, %s)', (user_id, username))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Error as e:
        print(f"DB error in add_user: {e}")
        return False

def upsert_user(user_id: int, username: Optional[str], full_name: Optional[str]):
    """Insert or update user in users table on /start."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, full_name, first_seen)
            VALUES (%s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE username=VALUES(username), full_name=VALUES(full_name)
        ''', (user_id, username, full_name))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Error as e:
        print(f"DB error in upsert_user: {e}")
        return False

def get_user_by_id(user_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return user
    except Error as e:
        print(f"DB error in get_user_by_id: {e}")
        return None

def list_all_users():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM users ORDER BY first_seen ASC')
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return users
    except Error as e:
        print(f"DB error in list_all_users: {e}")
        return []

def add_allowed_user_from_user(user: dict) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('REPLACE INTO allowed_users (user_id, username) VALUES (%s, %s)', (user['user_id'], user['username']))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Error as e:
        print(f"DB error in add_allowed_user_from_user: {e}")
        return False

def remove_user(user_id: int) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM allowed_users WHERE user_id = %s', (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Error as e:
        print(f"DB error in remove_user: {e}")
        return False

def list_allowed_users() -> List[Dict]:
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT user_id, username, added_at FROM allowed_users ORDER BY added_at DESC')
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except Error as e:
        print(f"DB error in list_allowed_users: {e}")
        return []
