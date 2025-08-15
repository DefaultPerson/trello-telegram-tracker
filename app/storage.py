import json
import logging
import os
from datetime import datetime
from typing import Dict, List

import aiofiles

PINNED_MESSAGES_FILE = "bot_pinned_messages.json"
USER_MAPPINGS_FILE = "user_mappings.json"
CARD_STATES_FILE = "card_states.json"


class Storage:
    """Class for handling JSON file storage operations"""

    @staticmethod
    async def load_json_file(filename: str, default_value: dict) -> dict:
        """Load JSON file asynchronously"""
        try:
            if os.path.exists(filename):
                async with aiofiles.open(filename, "r", encoding="utf-8") as f:
                    content = await f.read()
                    return json.loads(content)
        except Exception as e:
            logging.error("Failed to load %s: %s", filename, e)
        return default_value

    @staticmethod
    async def save_json_file(filename: str, data: dict):
        """Save JSON file asynchronously"""
        try:
            async with aiofiles.open(filename, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logging.error("Failed to save %s: %s", filename, e)

    async def load_pinned_messages(self):
        """Load pinned message data from file with new structure"""
        data = await self.load_json_file(PINNED_MESSAGES_FILE, {"messages": []})

        # Handle old format conversion
        if isinstance(data, dict) and any(
            key.startswith("-") for key in data.keys() if key != "messages"
        ):
            logging.info("Converting old format to new format")
            new_data = {"messages": []}
            for chat_id, messages in data.items():
                if isinstance(messages, list):
                    for msg in messages:
                        new_data["messages"].append(
                            {
                                "chat_id": chat_id,
                                "message_id": msg["message_id"],
                                "pinned_at": msg.get("pinned_at", "unknown"),
                                "message_url": msg.get("message_url", ""),
                            }
                        )
            await self.save_json_file(PINNED_MESSAGES_FILE, new_data)
            return new_data

        if "messages" not in data:
            data = {"messages": []}
        return data

    async def load_user_mappings(self):
        """Load Telegram username to Trello username mappings"""
        return await self.load_json_file(USER_MAPPINGS_FILE, {})

    async def load_card_states(self):
        """Load card states for tracking progress duration"""
        return await self.load_json_file(CARD_STATES_FILE, {})

    async def save_card_states(self, states: dict):
        """Save card states"""
        await self.save_json_file(CARD_STATES_FILE, states)

    async def add_pinned_message(
        self, chat_id: str, message_id: int, message_url: str = ""
    ):
        """Add a pinned message to storage"""
        data = await self.load_pinned_messages()

        # Check for duplicates
        existing = [
            msg
            for msg in data["messages"]
            if msg["chat_id"] == chat_id and msg["message_id"] == message_id
        ]
        if existing:
            return

        data["messages"].append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "pinned_at": datetime.now().isoformat(),
                "message_url": message_url,
            }
        )

        await self.save_json_file(PINNED_MESSAGES_FILE, data)

    async def get_stored_pinned_messages(self, chat_id: str):
        """Get stored pinned messages for a chat"""
        data = await self.load_pinned_messages()
        return [msg for msg in data["messages"] if msg["chat_id"] == chat_id]

    async def remove_pinned_message(self, chat_id: str, message_id: int):
        """Remove a pinned message from storage"""
        data = await self.load_pinned_messages()
        data["messages"] = [
            msg
            for msg in data["messages"]
            if not (msg["chat_id"] == chat_id and msg["message_id"] == message_id)
        ]
        await self.save_json_file(PINNED_MESSAGES_FILE, data)

    async def get_last_report_url(self, chat_id: str):
        """Get URL of the last report message"""
        stored = await self.get_stored_pinned_messages(chat_id)
        if stored:
            latest = max(stored, key=lambda x: x.get("pinned_at", ""))
            return latest.get("message_url", "")
        return ""
