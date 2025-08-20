import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional, Set

USERS_FILE = 'users.json'
ALLOWED_USERS_FILE = 'allowed_users.json'

# In-memory cache for allowed user IDs for performance
_allowed_user_ids_cache: Set[int] = set()

# --- Cache Management ---

def load_allowed_users_cache():
    """Loads allowed user IDs from the file into the in-memory cache."""
    global _allowed_user_ids_cache
    logging.info("Loading allowed users into cache...")
    allowed_users = load_json(ALLOWED_USERS_FILE)
    _allowed_user_ids_cache = {user['id'] for user in allowed_users}
    logging.info(f"Loaded {len(_allowed_user_ids_cache)} allowed users into cache.")

# --- Utility Functions ---

def load_json(filename: str) -> List[Dict]:
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_json(filename: str, data: List[Dict]):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- General User Management ---

def upsert_user(user_id: int, username: str, first_name: str) -> bool:
    users = load_json(USERS_FILE)
    if any(u['id'] == user_id for u in users):
        return True  # Already exists
    
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
    return next((user for user in users if user['id'] == user_id), None)

def list_all_users() -> List[Dict]:
    return load_json(USERS_FILE)

# --- Allowed Users Management (with Caching) ---

def add_allowed_user_from_user(user: Dict) -> bool:
    """Adds a user to the allowed list and updates the cache."""
    user_id = user['id']
    if user_id in _allowed_user_ids_cache:
        return True  # Already allowed

    allowed_list = load_json(ALLOWED_USERS_FILE)
    allowed_list.append(user)
    save_json(ALLOWED_USERS_FILE, allowed_list)
    
    # Update cache
    _allowed_user_ids_cache.add(user_id)
    return True

def list_allowed_users() -> List[Dict]:
    return load_json(ALLOWED_USERS_FILE)

def remove_allowed_user(user_id: int) -> bool:
    """Removes a user from the allowed list and updates the cache."""
    if user_id not in _allowed_user_ids_cache:
        return False # Not found in cache, so not in file either

    allowed_list = load_json(ALLOWED_USERS_FILE)
    initial_count = len(allowed_list)
    new_allowed = [u for u in allowed_list if u['id'] != user_id]

    if len(new_allowed) == initial_count:
        return False # Should not happen if cache is consistent

    save_json(ALLOWED_USERS_FILE, new_allowed)
    
    # Update cache
    _allowed_user_ids_cache.remove(user_id)
    return True

def is_user_allowed(user_id: int) -> bool:
    """Checks if a user is allowed using the in-memory cache."""
    return user_id in _allowed_user_ids_cache
