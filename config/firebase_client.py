import os
import uuid
import base64
import urllib.parse
from typing import Optional
from dotenv import load_dotenv

env_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    load_dotenv()

is_firebase_initialized = False
_storage_bucket = None

try:
    import firebase_admin
    from firebase_admin import credentials, storage

    cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
    private_key = os.getenv("FIREBASE_PRIVATE_KEY")
    storage_bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")

    found_path = None
    if cred_path:
        possible_paths = [
            cred_path,
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", cred_path)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "serviceAccountKey.json")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ServiceAccountKey.json")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ServiceAccountKey.json.json")),
        ]
        found_path = next((p for p in possible_paths if os.path.exists(p)), None)

    if not storage_bucket_name:
        # Default bucket naming for Firebase projects
        pid = project_id or "user-management-3ea6d"
        storage_bucket_name = f"{pid}.firebasestorage.app"

    if found_path:
        cred = credentials.Certificate(found_path)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, {"storageBucket": storage_bucket_name})
        is_firebase_initialized = True
        print(f"[Firebase Admin] Storage initialized via key: {os.path.basename(found_path)} (bucket: {storage_bucket_name})")
    elif project_id and client_email and private_key:
        clean_key = private_key.replace("\\n", "\n")
        cred = credentials.Certificate({
            "project_id": project_id,
            "client_email": client_email,
            "private_key": clean_key,
        })
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, {"storageBucket": storage_bucket_name})
        is_firebase_initialized = True
        print(f"[Firebase Admin] Storage initialized via environment credentials (bucket: {storage_bucket_name})")
    else:
        print("[Firebase Admin] Storage credentials not configured. Operating in simulated resilient mode.")
except Exception as e:
    print(f"[Firebase Admin] Storage initialization notice: {e}")


def upload_profile_picture(
    file_bytes: bytes,
    filename: str,
    content_type: str = "image/jpeg",
    client_id: str = "default",
) -> str:
    """
    Uploads a user profile picture to Firebase Storage and returns its public URL.
    Falls back gracefully to a data URI if Firebase Storage is offline or unconfigured.
    """
    if not file_bytes:
        return ""

    clean_client = str(client_id).replace("-", "_").replace(" ", "_")
    safe_name = os.path.basename(filename) if filename else "avatar.jpg"
    unique_blob_path = f"avatars/{clean_client}/{uuid.uuid4().hex}_{safe_name}"

    if is_firebase_initialized:
        try:
            bucket = storage.bucket()
            blob = bucket.blob(unique_blob_path)
            blob.upload_from_string(file_bytes, content_type=content_type)

            # Try to make public
            try:
                blob.make_public()
                if blob.public_url:
                    print(f"[Firebase Storage] Uploaded public avatar: {blob.public_url}")
                    return blob.public_url
            except Exception as acl_err:
                print(f"[Firebase Storage] make_public notice ({acl_err}), generating direct media URL.")

            # Fallback to standard Firebase Storage media URL
            encoded_path = urllib.parse.quote(unique_blob_path, safe="")
            media_url = f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/{encoded_path}?alt=media"
            print(f"[Firebase Storage] Uploaded media URL: {media_url}")
            return media_url
        except Exception as upload_err:
            print(f"[Firebase Storage] Upload warning ({upload_err}), using data URI fallback.")

    # Resilient fallback: base64 data URI
    b64_str = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{content_type};base64,{b64_str}"
