"""
AI Reply Drafter Plugin
Generates draft replies for scraped comments using Gemini.
"""
import os
import time
import requests

from plugins import Plugin


class AIReplyDrafter(Plugin):
    """Generate AI draft replies for comments."""

    name = "ai_reply_drafter"
    description = "Generates draft replies for comments with Gemini"
    enabled = True

    def process_posts(self, posts):
        """No-op for posts."""
        return posts

    def process_comments(self, comments):
        """Add AI draft replies to selected comments."""
        for comment in comments:
            comment.setdefault("ai_draft_reply", "")
            comment.setdefault("ai_reply_model", "")
            comment.setdefault("ai_reply_status", "pending")

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("   AI reply drafter skipped: GEMINI_API_KEY not set")
            for comment in comments:
                comment["ai_reply_status"] = "skipped_no_api_key"
            return comments

        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        max_comments = self._safe_int(os.getenv("AI_REPLY_MAX_COMMENTS", "1000"), 1000)
        min_score = self._safe_int(os.getenv("AI_REPLY_MIN_SCORE", "0"), 0)
        min_length = self._safe_int(os.getenv("AI_REPLY_MIN_LENGTH", "1"), 1)
        timeout = self._safe_int(os.getenv("AI_REPLY_TIMEOUT", "20"), 20)

        comments_by_id = {
            str(comment.get("comment_id")): comment
            for comment in comments
            if comment.get("comment_id")
        }

        generated = 0
        failed = 0
        skipped = 0
        for comment in comments:
            if generated >= max_comments:
                comment["ai_reply_status"] = "skipped_limit"
                skipped += 1
                continue

            body = self._safe_text(comment.get("body"))
            if not body or body in {"[deleted]", "[removed]"}:
                comment["ai_reply_status"] = "skipped_empty"
                skipped += 1
                continue

            score = self._safe_int(comment.get("score", 0), 0)
            if score < min_score or len(body) < min_length:
                comment["ai_reply_status"] = "skipped_filter"
                skipped += 1
                continue

            parent_body = ""
            parent_id = str(comment.get("parent_id") or "")
            if parent_id.startswith("t1_"):
                parent_comment = comments_by_id.get(parent_id[3:])
                if parent_comment:
                    parent_body = self._safe_text(parent_comment.get("body"))

            post_title = self._safe_text(comment.get("post_title"))
            post_selftext = self._safe_text(comment.get("post_selftext"))

            draft = self._generate_reply(
                comment_text=body,
                api_key=api_key,
                model=model,
                timeout=timeout,
                post_title=post_title,
                post_selftext=post_selftext,
                parent_comment_text=parent_body
            )
            if not draft:
                comment["ai_reply_status"] = "failed_generation"
                comment["ai_reply_model"] = model
                failed += 1
                continue

            comment["ai_draft_reply"] = draft
            comment["ai_reply_model"] = model
            comment["ai_reply_status"] = "generated"
            print(f"   generated reply for comment {comment.get('comment_id', '')}")
            generated += 1
            time.sleep(0.1)

        print(f"   AI reply drafts: generated={generated}, failed={failed}, skipped={skipped}")
        return comments

    @staticmethod
    def _safe_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_text(value):
        if value is None:
            return ""
        try:
            text = str(value)
        except Exception:
            return ""
        if text.lower() == "nan":
            return ""
        return text.strip()

    @staticmethod
    def _generate_reply(comment_text, api_key, model, timeout, post_title="", post_selftext="", parent_comment_text=""):
        """Call Gemini API and return a concise reply draft."""
        normalized_model = model[7:] if model.startswith("models/") else model
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{normalized_model}:generateContent"

        post_context = f"Post title: {post_title}\nPost text: {post_selftext[:800]}" if post_title or post_selftext else "Post context: unavailable"
        parent_context = f"Parent comment: {parent_comment_text[:800]}" if parent_comment_text else "Parent comment: unavailable"

        prompt = (
            "Draft one concise Reddit reply in 1 to 3 sentences. "
            "Be helpful, respectful, and neutral. "
            "Do not use markdown, hashtags, or emojis. "
            "Use the post and parent-comment context when relevant.\n\n"
            f"{post_context}\n\n"
            f"{parent_context}\n\n"
            f"Current comment:\n{comment_text}"
        )

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.6,
                "maxOutputTokens": 140
            }
        }

        try:
            response = requests.post(
                endpoint,
                params={"key": api_key},
                json=payload,
                timeout=timeout
            )
            if response.status_code != 200:
                return None

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [part.get("text", "").strip() for part in parts if part.get("text")]
            reply = " ".join(text_parts).strip()
            if not reply:
                return None

            if len(reply) > 700:
                reply = reply[:700].rsplit(" ", 1)[0].strip() + "..."

            return reply
        except Exception:
            return None
