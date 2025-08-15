import asyncio
import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand

from app import config
from app.handlers import CommandHandlers
from app.reports import ReportGenerator
from app.storage import Storage
from app.trello_api import TrelloAPI


class AsyncTrelloBot:
    """Main Trello Bot class"""

    def __init__(self):
        self.trello = TrelloAPI()
        self.storage = Storage()
        self.last_known_states = {}  # Store last known states of boards
        self.bot = Bot(token=config.TELEGRAM_API_TOKEN)
        self.dp = Dispatcher()
        self.bot_user_id = None  # Will be set after getting bot info

        # Initialize components
        self.reports = ReportGenerator(self.trello, self.storage)
        self.handlers = CommandHandlers(self, self.storage, self.reports)

        self._setup_handlers()

    def _setup_handlers(self):
        """Setup command handlers"""
        self.dp.message.register(self.handlers.handle_start_command, CommandStart())
        self.dp.message.register(
            self.handlers.handle_ct_command, Command(commands=["ct"])
        )
        self.dp.message.register(
            self.handlers.handle_wr_command, Command(commands=["wr"])
        )
        self.dp.message.register(
            self.handlers.handle_mt_command, Command(commands=["mt"])
        )
        self.dp.message.register(
            self.handlers.handle_stored_command, Command(commands=["stored"])
        )
        self.dp.message.register(
            self.handlers.handle_unpin_command, Command(commands=["unpin"])
        )
        self.dp.message.register(
            self.handlers.handle_clear_stored_command,
            Command(commands=["clear_stored"]),
        )
        self.dp.message.register(
            self.handlers.handle_debug_file_command, Command(commands=["debug_file"])
        )
        self.dp.message.register(
            self.handlers.handle_clear_commands_command,
            Command(commands=["clear_commands"]),
        )

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.bot.session.close()

    async def send_message(
        self,
        chat_id: str,
        message: str,
        parse_mode: ParseMode = ParseMode.HTML,
        max_retries: int = 10,
    ):
        """Send message to Telegram chat with retry mechanism"""
        for attempt in range(max_retries):
            try:
                result = await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True,
                )

                logging.info(
                    "Message sent successfully to %s on attempt %d",
                    chat_id,
                    attempt + 1,
                )
                return result

            except Exception as e:
                logging.error("Message send error on attempt %d: %s", attempt + 1, e)

            # Wait 5 seconds before retry (except on last attempt)
            if attempt < max_retries - 1:
                logging.info("Waiting 5 seconds before retry %d...", attempt + 2)
                await asyncio.sleep(5)

        logging.error("Failed to send message after %d attempts", max_retries)
        return None

    async def get_bot_info(self):
        """Get bot information"""
        try:
            bot_info = await self.bot.get_me()
            self.bot_user_id = bot_info.id
            logging.info("Bot ID: %d", self.bot_user_id)
            return True
        except Exception as e:
            logging.error("Failed to get bot info: %s", e)
            return False

    async def setup_bot_commands(self):
        """Setup bot commands menu"""
        try:
            # Define bot commands
            commands = [
                BotCommand(command="start", description="Show help and command list"),
                BotCommand(command="ct", description="Current report for all boards"),
                BotCommand(command="wr", description="Weekly statistics"),
                BotCommand(command="mt", description="My tasks (personal)"),
                BotCommand(command="stored", description="Show pinned messages"),
                BotCommand(command="unpin", description="Unpin message"),
                BotCommand(command="clear_stored", description="Clear stored messages"),
                BotCommand(command="debug_file", description="Show storage file"),
            ]

            # Clear old commands first (globally)
            await self.bot.delete_my_commands()
            logging.info("Cleared old bot commands")

            # Set new commands globally
            await self.bot.set_my_commands(commands)
            logging.info("Bot commands registered globally")

            # Also set commands for the specific chat if configured
            if hasattr(config, "PEER_ID") and config.PEER_ID:
                try:
                    from aiogram.types import BotCommandScopeChat

                    scope = BotCommandScopeChat(chat_id=config.PEER_ID)
                    await self.bot.set_my_commands(commands, scope=scope)
                    logging.info("Bot commands registered for chat %s", config.PEER_ID)
                except Exception as e:
                    logging.warning("Failed to set commands for specific chat: %s", e)

            return True

        except Exception as e:
            logging.error("Failed to setup bot commands: %s", e)
            return False

    async def clear_bot_commands(self):
        """Clear all bot commands"""
        try:
            # Clear global commands
            await self.bot.delete_my_commands()
            logging.info("Cleared global bot commands")

            # Clear commands for specific chat if configured
            if hasattr(config, "PEER_ID") and config.PEER_ID:
                try:
                    from aiogram.types import BotCommandScopeChat

                    scope = BotCommandScopeChat(chat_id=config.PEER_ID)
                    await self.bot.delete_my_commands(scope=scope)
                    logging.info("Cleared bot commands for chat %s", config.PEER_ID)
                except Exception as e:
                    logging.warning("Failed to clear commands for specific chat: %s", e)

            return True

        except Exception as e:
            logging.error("Failed to clear bot commands: %s", e)
            return False

    async def update_card_progress_tracking(self):
        """Update card progress tracking for long-running tasks"""
        card_states = await self.storage.load_card_states()
        current_time = datetime.now()

        for board_id in config.board_ids:
            try:
                cards = await self.trello.get_board_cards(board_id)
                lists = await self.trello.get_board_lists(board_id)
                list_names = {lst["id"]: lst["name"] for lst in lists}

                for card in cards:
                    card_key = "%s_%s" % (board_id, card["id"])
                    list_name = list_names.get(card["idList"], "")

                    # Check if card is in progress
                    is_in_progress = any(
                        name.lower() in list_name.lower()
                        for name in config.in_progress_list_names
                    )

                    if is_in_progress:
                        if card_key not in card_states:
                            # First time seeing this card in progress
                            card_states[card_key] = {
                                "started_at": current_time.isoformat(),
                                "board_id": board_id,
                                "card_name": card["name"],
                            }
                    else:
                        # Card is not in progress anymore, remove from tracking
                        if card_key in card_states:
                            del card_states[card_key]

            except Exception as e:
                logging.error(
                    "Error updating card progress for board %s: %s", board_id, e
                )

        await self.storage.save_card_states(card_states)

    async def check_for_completed_cards(self):
        """Check for newly completed cards and notify"""
        for board_id in config.board_ids:
            try:
                board_info = await self.trello.get_board_info(board_id)
                board_name = board_info["name"]

                # Get current cards and lists
                current_cards = await self.trello.get_board_cards(board_id)
                lists = await self.trello.get_board_lists(board_id)
                list_names = {lst["id"]: lst["name"] for lst in lists}

                # Check for completed cards
                for card in current_cards:
                    list_name = list_names.get(card["idList"], "")

                    # Check if card is in a "done" list
                    is_completed = any(
                        done_name.lower() in list_name.lower()
                        for done_name in config.done_list_names
                    )

                    card_key = "%s_%s" % (board_id, card["id"])

                    if is_completed:
                        # Check if this is a newly completed card
                        if card_key not in self.last_known_states:
                            self.last_known_states[card_key] = {
                                "completed": is_completed,
                                "list_id": card["idList"],
                                "members": [m["id"] for m in card.get("members", [])],
                            }
                        elif not self.last_known_states[card_key]["completed"]:
                            # Card was not completed before, but is now
                            card_link = self.trello.format_card_link(card)
                            message = (
                                "✅ <b>Card completed!</b>\n\n🗂️ Board: %s\n📋 Card: %s"
                                % (board_name, card_link)
                            )

                            await self.send_message(config.REPORT_CHAT_ID, message)

                            # Update state
                            self.last_known_states[card_key]["completed"] = True
                            self.last_known_states[card_key]["list_id"] = card["idList"]
                    else:
                        # Check for member changes (new assignments)
                        current_members = set(m["id"] for m in card.get("members", []))

                        if card_key in self.last_known_states:
                            previous_members = set(
                                self.last_known_states[card_key].get("members", [])
                            )
                            new_members = current_members - previous_members

                            if new_members:
                                # Notify about new member assignments
                                await self.notify_member_assignments(
                                    card, board_name, new_members
                                )

                        # Update state for non-completed cards
                        self.last_known_states[card_key] = {
                            "completed": False,
                            "list_id": card["idList"],
                            "members": list(current_members),
                        }

            except Exception as e:
                logging.error("Error checking board %s: %s", board_id, e)

    async def notify_member_assignments(
        self, card: dict, board_name: str, new_member_ids: set
    ):
        """Notify about new member assignments to a card"""
        try:
            # Get member info for new assignments
            new_members = []
            for member in card.get("members", []):
                if member["id"] in new_member_ids:
                    new_members.append(member)

            if not new_members:
                return

            # Create notification message with all new assignees
            member_tags = []
            for member in new_members:
                username = member.get("username", "")
                telegram_tag = config.trello_to_telegram_users.get(
                    username, "@%s" % username
                )
                member_tags.append(telegram_tag)

            tags_text = " ".join(member_tags)
            card_link = self.trello.format_card_link(card)

            message = "👥 <b>New assignments!</b>\n\n🗂️ Board: %s\n📋 Card: %s\n\n%s" % (
                board_name,
                card_link,
                tags_text,
            )

            await self.send_message(config.REPORT_CHAT_ID, message)

        except Exception as e:
            logging.error("Error notifying member assignments: %s", e)

    async def send_daily_report(self):
        """Send daily report with long-running task indicators"""
        try:
            # Update card progress tracking first
            await self.update_card_progress_tracking()

            # Generate enhanced report with long-running indicators
            report = await self.reports.generate_enhanced_daily_report()
            await self.handlers._send_report_with_pin(config.REPORT_CHAT_ID, report)
            logging.info("Daily report sent successfully")
        except Exception as e:
            logging.error("Failed to send daily report: %s", e)

    async def send_weekly_report(self):
        """Send weekly statistics report"""
        try:
            report = await self.reports.generate_weekly_stats_report()
            await self.send_message(config.REPORT_CHAT_ID, report)
            logging.info("Weekly statistics report sent successfully")
        except Exception as e:
            logging.error("Failed to send weekly report: %s", e)
