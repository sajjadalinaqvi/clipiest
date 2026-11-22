"""Clipiest Social Media Accounts and Direct Multi-Platform Publishing Engine.
Supports YouTube Shorts, TikTok, and Instagram Reels direct uploads.
"""
import json
import time
import re
import copy
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
from ..config import DATA_DIR

ACCOUNTS_FILE = DATA_DIR / "social_accounts.json"

DEFAULT_SETTINGS = {
    "youtube": {
        "connected": False,
        "channel_title": "",
        "channel_id": "",
        "client_id": "",
        "client_secret": "",
        "access_token": "",
        "refresh_token": "",
        "token_expiry": 0,
        "default_privacy": "public",  # public, unlisted, private
        "auto_shorts_tag": True,
        "category_id": "20",  # 20 = Gaming, 24 = Entertainment
    },
    "tiktok": {
        "connected": False,
        "username": "",
        "display_name": "",
        "access_token": "",
        "open_id": "",
        "default_privacy": "PUBLIC_TO_EVERYONE",  # PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, SELF_ONLY
        "allow_duet": True,
        "allow_stitch": True,
        "allow_comments": True,
    },
    "instagram": {
        "connected": False,
        "account_name": "",
        "instagram_account_id": "",
        "page_id": "",
        "access_token": "",
        "share_to_feed": True,
    },
    "defaults": {
        "auto_copy_hashtags": True,
        "caption_signature": "🔥 Clipped with @Clipiest",
        "default_tags": ["shorts", "viral", "fyp", "reels", "gaming", "streamer"]
    }
}

def load_accounts_data() -> Dict[str, Any]:
    """Loads social accounts data from disk, creating default structure if missing."""
    if not ACCOUNTS_FILE.exists():
        initial = copy.deepcopy(DEFAULT_SETTINGS)
        save_accounts_data(initial)
        return initial
    try:
        data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        defaults = copy.deepcopy(DEFAULT_SETTINGS)
        for platform, default_vals in defaults.items():
            if platform not in data:
                data[platform] = default_vals
            elif isinstance(default_vals, dict):
                for k, v in default_vals.items():
                    if k not in data[platform]:
                        data[platform][k] = v
        return data
    except Exception:
        return copy.deepcopy(DEFAULT_SETTINGS)

def save_accounts_data(data: Dict[str, Any]) -> None:
    """Safely saves social accounts data to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def mask_secret(val: str) -> str:
    """Masks secret tokens and keys for safe UI presentation."""
    if not val:
        return ""
    if len(val) <= 8:
        return "••••••••"
    return val[:4] + "••••••••" + val[-4:]

def get_masked_accounts() -> Dict[str, Any]:
    """Returns safe masked dictionary for the frontend."""
    raw = load_accounts_data()
    return {
        "youtube": {
            "connected": bool(raw["youtube"].get("connected")),
            "channel_title": raw["youtube"].get("channel_title", ""),
            "channel_id": raw["youtube"].get("channel_id", ""),
            "client_id": mask_secret(raw["youtube"].get("client_id", "")),
            "client_secret": mask_secret(raw["youtube"].get("client_secret", "")),
            "access_token": mask_secret(raw["youtube"].get("access_token", "")),
            "default_privacy": raw["youtube"].get("default_privacy", "public"),
            "auto_shorts_tag": raw["youtube"].get("auto_shorts_tag", True),
            "category_id": raw["youtube"].get("category_id", "20"),
        },
        "tiktok": {
            "connected": bool(raw["tiktok"].get("connected")),
            "username": raw["tiktok"].get("username", ""),
            "display_name": raw["tiktok"].get("display_name", ""),
            "access_token": mask_secret(raw["tiktok"].get("access_token", "")),
            "open_id": mask_secret(raw["tiktok"].get("open_id", "")),
            "default_privacy": raw["tiktok"].get("default_privacy", "PUBLIC_TO_EVERYONE"),
            "allow_duet": raw["tiktok"].get("allow_duet", True),
            "allow_stitch": raw["tiktok"].get("allow_stitch", True),
            "allow_comments": raw["tiktok"].get("allow_comments", True),
        },
        "instagram": {
            "connected": bool(raw["instagram"].get("connected")),
            "account_name": raw["instagram"].get("account_name", ""),
            "instagram_account_id": raw["instagram"].get("instagram_account_id", ""),
            "page_id": raw["instagram"].get("page_id", ""),
            "access_token": mask_secret(raw["instagram"].get("access_token", "")),
            "share_to_feed": raw["instagram"].get("share_to_feed", True),
        },
        "defaults": raw.get("defaults", DEFAULT_SETTINGS["defaults"])
    }

def update_account(platform: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Updates account fields for a specific platform."""
    if platform not in ("youtube", "tiktok", "instagram", "defaults"):
        raise ValueError(f"Unknown social platform: {platform}")
    data = load_accounts_data()
    target = data.setdefault(platform, {})
    for k, v in fields.items():
        if isinstance(v, str) and "••••" in v:
            continue  # Retain existing masked secret
        target[k] = v

    # Auto-flag connected if credentials are present
    if platform == "youtube":
        has_creds = bool(target.get("access_token") or (target.get("client_id") and target.get("client_secret")))
        target["connected"] = fields.get("connected", has_creds)
    elif platform == "tiktok":
        target["connected"] = fields.get("connected", bool(target.get("access_token")))
    elif platform == "instagram":
        target["connected"] = fields.get("connected", bool(target.get("access_token") and target.get("instagram_account_id")))

    save_accounts_data(data)
    return get_masked_accounts()

def disconnect_account(platform: str) -> Dict[str, Any]:
    """Disconnects and resets account fields for a specific platform."""
    if platform not in ("youtube", "tiktok", "instagram"):
        raise ValueError(f"Unknown social platform: {platform}")
    data = load_accounts_data()
    data[platform] = copy.deepcopy(DEFAULT_SETTINGS[platform])
    save_accounts_data(data)
    return get_masked_accounts()

def test_account_connection(platform: str) -> Dict[str, Any]:
    """Tests connection to the specified social platform API."""
    data = load_accounts_data()
    creds = data.get(platform, {})

    if platform == "youtube":
        token = creds.get("access_token", "").strip()
        if not token:
            return {
                "success": False,
                "message": "No YouTube access token configured. Provide an OAuth2 Access Token or Client credentials."
            }
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            if r.status_code == 200:
                res_data = r.json()
                items = res_data.get("items", [])
                if items:
                    title = items[0]["snippet"].get("title", "YouTube Channel")
                    creds["channel_title"] = title
                    creds["channel_id"] = items[0].get("id", "")
                    creds["connected"] = True
                    save_accounts_data(data)
                    return {"success": True, "message": f"Successfully connected to YouTube channel: {title}!"}
            return {
                "success": False,
                "message": f"YouTube API returned error ({r.status_code}): {r.text[:200]}"
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to reach YouTube API: {e}"}

    elif platform == "tiktok":
        token = creds.get("access_token", "").strip()
        if not token:
            return {
                "success": False,
                "message": "No TikTok Access Token configured. Add your Content Posting API token."
            }
        try:
            r = requests.get(
                "https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,display_name",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            if r.status_code == 200:
                res_data = r.json()
                user = res_data.get("data", {}).get("user", {})
                dname = user.get("display_name", "TikTok Creator")
                creds["display_name"] = dname
                creds["connected"] = True
                save_accounts_data(data)
                return {"success": True, "message": f"Successfully connected to TikTok account: {dname}!"}
            return {
                "success": False,
                "message": f"TikTok API error ({r.status_code}): {r.text[:200]}"
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to reach TikTok API: {e}"}

    elif platform == "instagram":
        token = creds.get("access_token", "").strip()
        ig_id = creds.get("instagram_account_id", "").strip()
        if not token:
            return {
                "success": False,
                "message": "No Instagram / Meta Graph API access token configured."
            }
        try:
            target_id = ig_id if ig_id else "me"
            r = requests.get(
                f"https://graph.facebook.com/v19.0/{target_id}?fields=id,username,name&access_token={token}",
                timeout=10
            )
            if r.status_code == 200:
                user = r.json()
                uname = user.get("username") or user.get("name") or "Instagram Account"
                creds["account_name"] = f"@{uname}" if not uname.startswith("@") else uname
                creds["instagram_account_id"] = user.get("id", ig_id)
                creds["connected"] = True
                save_accounts_data(data)
                return {"success": True, "message": f"Successfully connected to Instagram Reels: {creds['account_name']}!"}
            return {
                "success": False,
                "message": f"Instagram Graph API error ({r.status_code}): {r.text[:200]}"
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to reach Instagram Graph API: {e}"}

    return {"success": False, "message": "Unknown platform."}

def publish_clip(
    clip_path: Path,
    platforms: List[str],
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    privacy: str = "public",
) -> Dict[str, Any]:
    """Publishes a rendered 9:16 vertical video clip to selected social platforms."""
    if not clip_path.exists():
        raise FileNotFoundError(f"Video file not found: {clip_path}")

    tags = tags or ["shorts", "reels", "viral", "fyp"]
    accounts = load_accounts_data()
    results = {}

    for platform in platforms:
        p = platform.lower().strip()
        creds = accounts.get(p, {})

        if p == "youtube":
            results["youtube"] = _publish_youtube(clip_path, creds, title, description, tags, privacy)
        elif p == "tiktok":
            results["tiktok"] = _publish_tiktok(clip_path, creds, title, description, tags, privacy)
        elif p == "instagram":
            results["instagram"] = _publish_instagram(clip_path, creds, title, description, tags, privacy)
        else:
            results[p] = {"success": False, "error": f"Unsupported platform: {p}"}

    return {
        "file": clip_path.name,
        "platforms": results,
        "timestamp": time.time()
    }

def _publish_youtube(clip_path: Path, creds: Dict[str, Any], title: str, description: str, tags: List[str], privacy: str) -> Dict[str, Any]:
    """Uploads video to YouTube Shorts."""
    token = creds.get("access_token", "").strip()
    if not token:
        # If no real token is stored yet, simulate successful verification / mock upload for staging
        yt_title = title if "#Shorts" in title else f"{title} #Shorts"
        return {
            "success": True,
            "status": "ready_for_auth",
            "platform": "YouTube Shorts",
            "title": yt_title,
            "privacy": privacy or creds.get("default_privacy", "public"),
            "url": "https://youtube.com/shorts/",
            "message": "YouTube Shorts metadata staged. Add an OAuth2 Access Token in Settings > Connected Accounts to publish live to your channel."
        }

    try:
        yt_title = title if "#Shorts" in title else f"{title} #Shorts"
        full_desc = f"{description}\n\nTags: {' '.join('#' + t.lstrip('#') for t in tags)}\n\nClipped with Clipiest"
        category = creds.get("category_id", "20")
        priv = privacy if privacy in ("public", "unlisted", "private") else creds.get("default_privacy", "public")

        metadata = {
            "snippet": {
                "title": yt_title[:100],
                "description": full_desc[:5000],
                "tags": [t.lstrip("#") for t in tags],
                "categoryId": category,
            },
            "status": {
                "privacyStatus": priv,
                "selfDeclaredMadeForKids": False
            }
        }

        # Step 1: Resumable upload session creation
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(clip_path.stat().st_size)
        }
        init_res = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers=headers,
            json=metadata,
            timeout=15
        )

        if init_res.status_code == 200:
            upload_url = init_res.headers.get("Location")
            if not upload_url:
                return {"success": False, "error": "No upload URL returned from YouTube API."}

            # Step 2: Upload file bytes
            with clip_path.open("rb") as f:
                put_res = requests.put(
                    upload_url,
                    data=f,
                    headers={"Content-Type": "video/mp4"},
                    timeout=180
                )

            if put_res.status_code in (200, 201):
                vid_data = put_res.json()
                video_id = vid_data.get("id", "")
                return {
                    "success": True,
                    "platform": "YouTube Shorts",
                    "video_id": video_id,
                    "url": f"https://youtube.com/shorts/{video_id}",
                    "message": f"Successfully published to YouTube Shorts: https://youtube.com/shorts/{video_id}"
                }
            return {"success": False, "error": f"Failed uploading video bytes to YouTube: {put_res.text[:200]}"}

        return {"success": False, "error": f"YouTube resumable session error: {init_res.text[:200]}"}
    except Exception as e:
        return {"success": False, "error": f"YouTube upload exception: {str(e)}"}

def _publish_tiktok(clip_path: Path, creds: Dict[str, Any], title: str, description: str, tags: List[str], privacy: str) -> Dict[str, Any]:
    """Uploads video to TikTok via Content Posting API."""
    token = creds.get("access_token", "").strip()
    if not token:
        return {
            "success": True,
            "status": "ready_for_auth",
            "platform": "TikTok",
            "title": title,
            "privacy": privacy or creds.get("default_privacy", "PUBLIC_TO_EVERYONE"),
            "url": "https://www.tiktok.com/",
            "message": "TikTok metadata staged. Add a TikTok Access Token in Settings > Connected Accounts to publish live."
        }

    try:
        post_title = f"{title} {' '.join('#' + t.lstrip('#') for t in tags[:6])}"[:150]
        payload = {
            "post_info": {
                "title": post_title,
                "privacy_level": creds.get("default_privacy", "PUBLIC_TO_EVERYONE"),
                "disable_duet": not creds.get("allow_duet", True),
                "disable_stitch": not creds.get("allow_stitch", True),
                "disable_comment": not creds.get("allow_comments", True),
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": clip_path.stat().st_size,
                "chunk_size": clip_path.stat().st_size,
                "total_chunk_count": 1
            }
        }
        res = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        if res.status_code == 200:
            res_data = res.json().get("data", {})
            publish_id = res_data.get("publish_id", "")
            upload_url = res_data.get("upload_url", "")
            if upload_url:
                with clip_path.open("rb") as f:
                    requests.put(upload_url, data=f, headers={"Content-Type": "video/mp4"}, timeout=180)
            return {
                "success": True,
                "platform": "TikTok",
                "publish_id": publish_id,
                "url": f"https://www.tiktok.com/",
                "message": f"Successfully initiated upload to TikTok (Publish ID: {publish_id})."
            }
        return {"success": False, "error": f"TikTok initialization error: {res.text[:200]}"}
    except Exception as e:
        return {"success": False, "error": f"TikTok upload exception: {str(e)}"}

def _publish_instagram(clip_path: Path, creds: Dict[str, Any], title: str, description: str, tags: List[str], privacy: str) -> Dict[str, Any]:
    """Uploads video to Instagram Reels via Meta Graph API."""
    token = creds.get("access_token", "").strip()
    ig_user_id = creds.get("instagram_account_id", "").strip()
    if not token or not ig_user_id:
        return {
            "success": True,
            "status": "ready_for_auth",
            "platform": "Instagram Reels",
            "title": title,
            "url": "https://www.instagram.com/reels/",
            "message": "Instagram Reels metadata staged. Add your Instagram Account ID & Access Token in Settings > Connected Accounts to publish live."
        }

    try:
        caption = f"{title}\n\n{description}\n\n{' '.join('#' + t.lstrip('#') for t in tags[:10])}\n\n@Clipiest"
        # Create media container
        init_res = requests.post(
            f"https://graph.facebook.com/v19.0/{ig_user_id}/media",
            data={
                "media_type": "REELS",
                "caption": caption[:2200],
                "share_to_feed": creds.get("share_to_feed", True),
                "access_token": token
            },
            timeout=15
        )
        if init_res.status_code == 200:
            creation_id = init_res.json().get("id")
            # Publish container
            pub_res = requests.post(
                f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish",
                data={
                    "creation_id": creation_id,
                    "access_token": token
                },
                timeout=20
            )
            if pub_res.status_code == 200:
                media_id = pub_res.json().get("id", "")
                return {
                    "success": True,
                    "platform": "Instagram Reels",
                    "media_id": media_id,
                    "url": f"https://www.instagram.com/p/{media_id}/",
                    "message": f"Successfully published Reel to Instagram (Media ID: {media_id})!"
                }
            return {"success": False, "error": f"Failed publishing Instagram Reel: {pub_res.text[:200]}"}
        return {"success": False, "error": f"Instagram container creation error: {init_res.text[:200]}"}
    except Exception as e:
        return {"success": False, "error": f"Instagram upload exception: {str(e)}"}
