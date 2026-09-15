import os
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

env_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    load_dotenv()
from bson import ObjectId
from pymongo import MongoClient

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "user_platform")

_mongo_client: Optional[MongoClient] = None
_db = None
is_connected = False

FALLBACK_FILE = (
    os.path.join(os.environ.get("TMPDIR", "/tmp"), ".mongo_fallback.json")
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    else os.path.join(os.path.dirname(__file__), "..", ".mongo_fallback.json")
)


def _load_fallback() -> Dict[str, List[Dict[str, Any]]]:
    try:
        if os.path.exists(FALLBACK_FILE):
            with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[MongoDB Fallback] Read error: {e}")
    return {"users": [], "activity_logs": []}


def _save_fallback(data: Dict[str, Any]):
    try:
        with open(FALLBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        print(f"[MongoDB Fallback] Write error: {e}")


def _match_item(item: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for key, val in query.items():
        if key == "$or" and isinstance(val, list):
            any_match = any(_match_item(item, sub) for sub in val)
            if not any_match:
                return False
            continue

        if key == "_id":
            target_id = str(val)
            item_id = str(item.get("_id", ""))
            if item_id != target_id:
                return False
            continue

        if isinstance(val, dict) and "$regex" in val:
            pattern = val["$regex"]
            flags = re.IGNORECASE if "i" in val.get("$options", "") else 0
            if not re.search(pattern, str(item.get(key, "")), flags):
                return False
            continue

        if item.get(key) != val:
            return False
    return True


class FallbackCursor:
    def __init__(self, items: List[Dict[str, Any]]):
        self._items = items
        self._sort_key = None
        self._sort_dir = 1
        self._skip = 0
        self._limit = None

    def sort(self, key_or_list, direction=1):
        if isinstance(key_or_list, list) and len(key_or_list) > 0:
            self._sort_key, self._sort_dir = key_or_list[0]
        elif isinstance(key_or_list, str):
            self._sort_key = key_or_list
            self._sort_dir = direction
        return self

    def skip(self, n: int):
        self._skip = n
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def to_list(self) -> List[Dict[str, Any]]:
        res = list(self._items)
        if self._sort_key:
            res.sort(
                key=lambda x: str(x.get(self._sort_key, "")),
                reverse=(self._sort_dir == -1)
            )
        if self._skip:
            res = res[self._skip:]
        if self._limit is not None:
            res = res[:self._limit]
        return res

    def __iter__(self):
        return iter(self.to_list())


class FallbackCollection:
    def __init__(self, name: str):
        self.name = name

    def _get_items(self):
        data = _load_fallback()
        if self.name not in data:
            data[self.name] = []
        return data, data[self.name]

    def insert_one(self, doc: Dict[str, Any]):
        data, items = self._get_items()
        new_doc = dict(doc)
        if "_id" not in new_doc:
            new_doc["_id"] = str(ObjectId())
        else:
            new_doc["_id"] = str(new_doc["_id"])
        if "created_at" not in new_doc:
            new_doc["created_at"] = datetime.now(timezone.utc).isoformat()
        items.append(new_doc)
        _save_fallback(data)
        
        class InsertResult:
            inserted_id = new_doc["_id"]
        return InsertResult()

    def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        _, items = self._get_items()
        for item in items:
            if _match_item(item, query):
                return item
        return None

    def find(self, query: Dict[str, Any] = None) -> FallbackCursor:
        if query is None:
            query = {}
        _, items = self._get_items()
        matched = [it for it in items if _match_item(it, query)]
        return FallbackCursor(matched)

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any]):
        data, items = self._get_items()
        idx = -1
        for i, item in enumerate(items):
            if _match_item(item, query):
                idx = i
                break
        if idx == -1:
            class NoUpdate:
                matched_count = 0
                modified_count = 0
            return NoUpdate()

        if "$set" in update:
            items[idx].update(update["$set"])
            items[idx]["updated_at"] = datetime.now(timezone.utc).isoformat()

        _save_fallback(data)
        class Updated:
            matched_count = 1
            modified_count = 1
        return Updated()

    def count_documents(self, query: Dict[str, Any] = None) -> int:
        if query is None:
            query = {}
        _, items = self._get_items()
        return sum(1 for it in items if _match_item(it, query))

    def create_index(self, *args, **kwargs):
        return True


class FallbackDatabase:
    def __getitem__(self, name: str):
        return FallbackCollection(name)

    def get_collection(self, name: str):
        return FallbackCollection(name)


def connect_mongodb():
    global _mongo_client, _db, is_connected
    try:
        _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
        _mongo_client.admin.command('ping')
        _db = _mongo_client[MONGODB_DB_NAME]
        is_connected = True

        # Indices
        try:
            _db.users.create_index([("client_id", 1), ("is_deleted", 1)])
            _db.users.create_index([("client_id", 1), ("email", 1)])
            _db.activity_logs.create_index([("client_id", 1), ("timestamp", -1)])
        except Exception as idx_err:
            print(f"[MongoDB] Index notice: {idx_err}")

        print(f"[MongoDB] Connected to database: {MONGODB_DB_NAME}")
    except Exception as e:
        print(f"[MongoDB] Connection to {MONGODB_URI} failed ({e}). Using persistent local fallback.")
        is_connected = False
        _db = FallbackDatabase()


def get_db():
    global _db
    if _db is None:
        connect_mongodb()
    return _db
