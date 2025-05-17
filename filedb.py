import json
import os
from datetime import datetime
from typing import List, Dict, Optional

USERS_FILE = 'users.json'
ALLOWED_USERS_FILE = 'allowed_users.json'

# Utility functions for file-based storage

def load_json(filename: str) -> List[Dict]:
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_json(filename: str, data: List[Dict]):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# User management

def upsert_user(user_id: int, username: str, first_name: str) -> bool:
    users = load_json(USERS_FILE)
    for user in users:
        if user['id'] == user_id:
            # Already exists, do not add again
            return True
    user_entry = {
        'id': user_id,
        'username': username or '',
        'first_name': first_name or '',
        'date_joined': datetime.now().isoformat()
    }
    users.append(user_entry)
    save_json(USERS_FILE, users)
    return True

def get_user_by_id(user_id: int) -> Optional[Dict]:
    users = load_json(USERS_FILE)
    for user in users:
        if user['id'] == user_id:
            return user
    return None

def list_all_users() -> List[Dict]:
    return load_json(USERS_FILE)

# Allowed users management

def add_allowed_user_from_user(user: Dict) -> bool:
    allowed = load_json(ALLOWED_USERS_FILE)
    for u in allowed:
        if u['id'] == user['id']:
            return True  # Already allowed
    allowed.append(user)
    save_json(ALLOWED_USERS_FILE, allowed)
    return True

def list_allowed_users() -> List[Dict]:
    return load_json(ALLOWED_USERS_FILE)

def remove_allowed_user(user_id: int) -> bool:
    allowed = load_json(ALLOWED_USERS_FILE)
    new_allowed = [u for u in allowed if u['id'] != user_id]
    if len(new_allowed) == len(allowed):
        return False  # Not found
    save_json(ALLOWED_USERS_FILE, new_allowed)
    return True

def is_user_allowed(user_id: int) -> bool:
    allowed = load_json(ALLOWED_USERS_FILE)
    return any(u['id'] == user_id for u in allowed)
