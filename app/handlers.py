import asyncio
import logging
import os

import aiofiles
from aiogram.types import Message

from app import config
from app.storage import PINNED_MESSAGES_FILE


class CommandHandlers:
    """Class for handling bot commands"""

    def __init__(self, bot, storage, reports):
        self.bot = bot
        self.storage = storage
        self.reports = reports

    async def handle_start_command(self, message: Message):
        """Handle /start command"""
        asyncio.create_task(self._handle_start_command_async(message))

    async def _handle_start_command_async(self, message: Message):
        """Handle /start command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        welcome_msg = """🤖 <b>Trello Bot activated!</b>

Available commands:
• /ct - Get current report for all boards
• /wr - Get weekly statistics
• /mt - My tasks (overdue and current)
• /stored - Show stored pinned messages
• /unpin MESSAGE_ID - Unpin message (for testing)
• /clear_stored - Clear stored message IDs
• /clear_commands - Clear bot commands
• /debug_file - Show storage file contents
• /start - Show this message

Bot automatically:
• Notifies about completed cards
• Notifies about member assignments
• Sends daily reports (Mon-Sat at 8:00 AM)
• Sends weekly statistics (Mon at 12:00 AM)

🐌 - card in progress for more than 3 days"""

        await self.bot.send_message(str(message.chat.id), welcome_msg)

    async def handle_ct_command(self, message: Message):
        """Handle /ct command"""
        asyncio.create_task(self._handle_ct_command_async(message))

    async def _handle_ct_command_async(self, message: Message):
        """Handle /ct command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        try:
            report = await self.reports.generate_enhanced_daily_report()
            await self._send_report_with_pin(str(message.chat.id), report)
        except Exception as e:
            error_msg = "❌ Error creating report: %s" % str(e)
            await self.bot.send_message(str(message.chat.id), error_msg)
            logging.error("Error in /ct command: %s", e)

    async def handle_wr_command(self, message: Message):
        """Handle /wr command"""
        asyncio.create_task(self._handle_wr_command_async(message))

    async def _handle_wr_command_async(self, message: Message):
        """Handle /wr command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        try:
            report = await self.reports.generate_weekly_stats_report()
            await self.bot.send_message(str(message.chat.id), report)
        except Exception as e:
            error_msg = "❌ Error creating weekly report: %s" % str(e)
            await self.bot.send_message(str(message.chat.id), error_msg)
            logging.error("Error in /wr command: %s", e)

    async def handle_mt_command(self, message: Message):
        """Handle /mt command"""
        asyncio.create_task(self._handle_mt_command_async(message))

    async def _handle_mt_command_async(self, message: Message):
        """Handle /mt command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        if not message.from_user or not message.from_user.username:
            await self.bot.send_message(
                str(message.chat.id), "❌ Could not determine your username"
            )
            return

        try:
            telegram_username = "@%s" % message.from_user.username
            tasks = await self.reports.get_user_tasks(telegram_username)

            if "error" in tasks:
                await self.bot.send_message(str(message.chat.id), tasks["error"])
                return

            # Format user tasks report (without tags)
            report_parts = ["👤 <b>My tasks (%s)</b>\n" % tasks["trello_username"]]

            if tasks["overdue"]:
                report_parts.append("⏰ <b>Overdue (%d):</b>" % len(tasks["overdue"]))
                for task in tasks["overdue"]:
                    report_parts.append(
                        "• <a href='%s'>%s</a>" % (task["url"], task["name"])
                    )
                    report_parts.append("  📋 %s → %s" % (task["board"], task["list"]))

            if tasks["current"]:
                report_parts.append("\n🔄 <b>Current (%d):</b>" % len(tasks["current"]))
                for task in tasks["current"]:
                    report_parts.append(
                        "• <a href='%s'>%s</a>" % (task["url"], task["name"])
                    )
                    report_parts.append("  📋 %s → %s" % (task["board"], task["list"]))

            if not tasks["overdue"] and not tasks["current"]:
                report_parts.append("✅ You have no active tasks!")

            await self.bot.send_message(str(message.chat.id), "\n".join(report_parts))

        except Exception as e:
            await self.bot.send_message(str(message.chat.id), "❌ Error: %s" % str(e))
            logging.error("Error in /mt command: %s", e)

    async def handle_unpin_command(self, message: Message):
        """Handle /unpin command"""
        asyncio.create_task(self._handle_unpin_command_async(message))

    async def _handle_unpin_command_async(self, message: Message):
        """Handle /unpin command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        try:
            parts = message.text.split(" ", 1)
            if len(parts) < 2:
                await self.bot.send_message(
                    str(message.chat.id), "❌ Usage: /unpin MESSAGE_ID"
                )
                return

            msg_id = int(parts[1])
            if await self._unpin_message(str(message.chat.id), msg_id):
                await self.bot.send_message(
                    str(message.chat.id), "✅ Message %d unpinned" % msg_id
                )
            else:
                await self.bot.send_message(
                    str(message.chat.id),
                    "❌ Failed to unpin message %d" % msg_id,
                )
        except (ValueError, IndexError):
            await self.bot.send_message(
                str(message.chat.id), "❌ Usage: /unpin MESSAGE_ID"
            )

    async def handle_stored_command(self, message: Message):
        """Handle /stored command"""
        asyncio.create_task(self._handle_stored_command_async(message))

    async def _handle_stored_command_async(self, message: Message):
        """Handle /stored command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        stored = await self.storage.get_stored_pinned_messages(str(message.chat.id))
        if stored:
            msg_list = "\n".join(
                [
                    "• %d (%s)" % (msg["message_id"], msg.get("pinned_at", "unknown"))
                    for msg in stored
                ]
            )
            await self.bot.send_message(
                str(message.chat.id),
                "📌 Stored pinned messages:\n%s" % msg_list,
            )
        else:
            await self.bot.send_message(
                str(message.chat.id), "📌 No stored pinned messages"
            )

    async def handle_clear_stored_command(self, message: Message):
        """Handle /clear_stored command"""
        asyncio.create_task(self._handle_clear_stored_command_async(message))

    async def _handle_clear_stored_command_async(self, message: Message):
        """Handle /clear_stored command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        data = await self.storage.load_pinned_messages()
        data["messages"] = [
            msg for msg in data["messages"] if msg["chat_id"] != str(message.chat.id)
        ]
        await self.storage.save_json_file(PINNED_MESSAGES_FILE, data)
        await self.bot.send_message(
            str(message.chat.id), "🗑️ All stored pinned messages cleared"
        )

    async def handle_debug_file_command(self, message: Message):
        """Handle /debug_file command"""
        asyncio.create_task(self._handle_debug_file_command_async(message))

    async def _handle_debug_file_command_async(self, message: Message):
        """Handle /debug_file command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        try:
            if os.path.exists(PINNED_MESSAGES_FILE):
                async with aiofiles.open(
                    PINNED_MESSAGES_FILE, "r", encoding="utf-8"
                ) as f:
                    content = await f.read()
                await self.bot.send_message(
                    str(message.chat.id),
                    "📄 File contents:\n<code>%s</code>" % content,
                )
            else:
                await self.bot.send_message(
                    str(message.chat.id),
                    "📄 File bot_pinned_messages.json does not exist",
                )
        except Exception as e:
            await self.bot.send_message(
                str(message.chat.id), "❌ Error reading file: %s" % str(e)
            )

    async def handle_clear_commands_command(self, message: Message):
        """Handle /clear_commands command"""
        asyncio.create_task(self._handle_clear_commands_command_async(message))

    async def _handle_clear_commands_command_async(self, message: Message):
        """Handle /clear_commands command asynchronously"""
        if str(message.chat.id) != str(config.PEER_ID):
            return

        try:
            if await self.bot.clear_bot_commands():
                await self.bot.send_message(
                    str(message.chat.id), "🗑️ All bot commands cleared"
                )
            else:
                await self.bot.send_message(
                    str(message.chat.id), "❌ Failed to clear bot commands"
                )
        except Exception as e:
            await self.bot.send_message(
                str(message.chat.id), "❌ Error clearing commands: %s" % str(e)
            )
            logging.error("Error in /clear_commands command: %s", e)

    # Helper methods
    async def _send_report_with_pin(self, chat_id: str, message: str):
        """Send report message and manage pinning"""
        # Get link to previous report
        previous_report_url = await self.storage.get_last_report_url(chat_id)
        if previous_report_url:
            message += "\n\n📎 <a href='%s'>Previous report</a>" % previous_report_url

        # Unpin old messages
        stored_pinned = await self.storage.get_stored_pinned_messages(chat_id)
        logging.info("Found %d stored pinned messages", len(stored_pinned))

        for msg_data in stored_pinned:
            old_msg_id = msg_data["message_id"]
            if await self._unpin_message(chat_id, old_msg_id):
                await self.storage.remove_pinned_message(chat_id, old_msg_id)
                logging.info("Unpinned message %d", old_msg_id)

        # Send new message
        result = await self.bot.send_message(chat_id, message)
        if not result:
            return result

        message_id = result.message_id

        # Generate message URL
        url_chat_id = chat_id[4:] if chat_id.startswith("-100") else chat_id
        message_url = "https://t.me/c/%s/%d" % (url_chat_id, message_id)

        # Pin new message
        if await self._pin_message(chat_id, message_id):
            await self.storage.add_pinned_message(chat_id, message_id, message_url)
            logging.info("Pinned new message %d", message_id)

        return result

    async def _pin_message(self, chat_id: str, message_id: int):
        """Pin a message"""
        try:
            await self.bot.bot.pin_chat_message(
                chat_id=chat_id,
                message_id=message_id,
                disable_notification=True,
            )
            return True
        except Exception as e:
            logging.error("Failed to pin message: %s", e)
            return False

    async def _unpin_message(self, chat_id: str, message_id: int):
        """Unpin a message"""
        try:
            await self.bot.bot.unpin_chat_message(
                chat_id=chat_id, message_id=message_id
            )
            return True
        except Exception as e:
            logging.error("Failed to unpin message: %s", e)
            return False
