import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from app import config


class ReportGenerator:
    """Class for generating various reports"""

    def __init__(self, trello_api, storage):
        self.trello = trello_api
        self.storage = storage

    def is_card_long_running(
        self, board_id: str, card_id: str, card_states: dict
    ) -> bool:
        """Check if card has been in progress for more than 3 days"""
        card_key = "%s_%s" % (board_id, card_id)
        if card_key in card_states:
            started_at = datetime.fromisoformat(card_states[card_key]["started_at"])
            return (datetime.now() - started_at).days >= 3
        return False

    def _is_card_done(self, card: dict, list_names: dict) -> bool:
        """Check if card is in a done list"""
        list_name = list_names.get(card["idList"], "")
        return any(
            done_name.lower() in list_name.lower()
            for done_name in config.done_list_names
        )

    async def get_user_tasks(self, telegram_username: str) -> Dict[str, List]:
        """Get tasks for a specific user based on Telegram username"""
        # Find Trello username for this Telegram user
        trello_username = None
        for trello_user, telegram_user in config.trello_to_telegram_users.items():
            if (
                telegram_user.replace("@", "").lower()
                == telegram_username.replace("@", "").lower()
            ):
                trello_username = trello_user
                break

        if not trello_username:
            return {"error": "User %s not found in settings" % telegram_username}

        overdue_tasks = []
        current_tasks = []

        for board_id in config.board_ids:
            try:
                # Get all data in parallel to speed up
                board_info_task = self.trello.get_board_info(board_id)
                cards_task = self.trello.get_board_cards(board_id)
                lists_task = self.trello.get_board_lists(board_id)

                # Wait for all data
                board_info, cards, lists = await asyncio.gather(
                    board_info_task, cards_task, lists_task
                )

                list_names = {lst["id"]: lst["name"] for lst in lists}

                # Filter cards assigned to this user (more efficient)
                user_cards = [
                    card
                    for card in cards
                    if card.get("members")
                    and any(
                        member.get("username") == trello_username
                        for member in card["members"]
                    )
                ]

                # Categorize user cards
                for card in user_cards:
                    # Skip done cards
                    list_name = list_names.get(card["idList"], "")
                    is_done = any(
                        done_name.lower() in list_name.lower()
                        for done_name in config.done_list_names
                    )
                    if is_done:
                        continue

                    card_info = {
                        "name": card["name"],
                        "url": card["shortUrl"],
                        "board": board_info["name"],
                        "list": list_name,
                    }

                    # Check overdue without additional API call
                    if self.trello.is_card_overdue(card):
                        overdue_tasks.append(card_info)
                    else:
                        # Check if card is in progress lists and should be current
                        is_in_progress = any(
                            name.lower() in list_name.lower()
                            for name in config.in_progress_list_names
                        )

                        if is_in_progress:
                            # Additional check: make sure task is not scheduled for future
                            start_date = card.get("start")
                            due_date = card.get("due")
                            now = datetime.now()

                            should_be_current = True

                            # If task has start date in future, don't show as current
                            if start_date:
                                try:
                                    start_dt = datetime.fromisoformat(
                                        start_date.replace("Z", "+00:00")
                                    )
                                    start_dt = start_dt.replace(tzinfo=None)
                                    if start_dt > now:
                                        should_be_current = False
                                except (ValueError, TypeError):
                                    pass  # If parsing fails, keep as current

                            # If task has due date in future but no start date, also check due date
                            elif due_date and not start_date:
                                try:
                                    due_dt = datetime.fromisoformat(
                                        due_date.replace("Z", "+00:00")
                                    )
                                    due_dt = due_dt.replace(tzinfo=None)
                                    # If due date is more than 3 days in future, might be scheduled for later
                                    if (due_dt - now).days > 3:
                                        should_be_current = False
                                except (ValueError, TypeError):
                                    pass

                            if should_be_current:
                                current_tasks.append(card_info)

            except Exception as e:
                logging.error(
                    "Error getting tasks for user %s from board %s: %s",
                    telegram_username,
                    board_id,
                    e,
                )

        return {
            "overdue": overdue_tasks,
            "current": current_tasks,
            "trello_username": trello_username,
        }

    async def generate_enhanced_daily_report(self) -> str:
        """Generate daily report with long-running task indicators"""
        card_states = await self.storage.load_card_states()
        report_parts = ["📊 <b>Daily Trello Report</b>\n"]

        total_overdue = 0
        total_current = 0

        for board_id in config.board_ids:
            try:
                board_info = await self.trello.get_board_info(board_id)
                board_name = board_info["name"]

                # Get all cards and lists
                all_cards = await self.trello.get_board_cards(board_id)
                lists = await self.trello.get_board_lists(board_id)
                list_names = {lst["id"]: lst["name"] for lst in lists}

                # Filter out done cards
                active_cards = [
                    card
                    for card in all_cards
                    if not self._is_card_done(card, list_names)
                ]

                # Get overdue and current cards
                overdue_cards = [
                    card for card in active_cards if self.trello.is_card_overdue(card)
                ]
                current_cards_result = await self.trello.get_current_cards(board_id)
                current_cards = [
                    card
                    for card in current_cards_result
                    if not self._is_card_done(card, list_names)
                ]

                total_overdue += len(overdue_cards)
                total_current += len(current_cards)

                if overdue_cards or current_cards:
                    report_parts.append("\n🗂️ <b>%s</b>" % board_name)

                    if overdue_cards:
                        report_parts.append(
                            "⏰ <b>Overdue cards (%d):</b>" % len(overdue_cards)
                        )
                        for card in overdue_cards:
                            card_link = self.trello.format_card_link(card)
                            assignees = self.trello.get_card_assignees_as_telegram_tags(
                                card
                            )
                            assignees_text = " - %s" % assignees if assignees else ""

                            # Add long-running indicator
                            long_running = (
                                "🐌 "
                                if self.is_card_long_running(
                                    board_id, card["id"], card_states
                                )
                                else ""
                            )

                            report_parts.append(
                                "• %s%s%s" % (long_running, card_link, assignees_text)
                            )

                    if current_cards:
                        report_parts.append(
                            "\n🔄 <b>Current (%d):</b>" % len(current_cards)
                        )
                        for card in current_cards:
                            card_link = self.trello.format_card_link(card)
                            assignees = self.trello.get_card_assignees_as_telegram_tags(
                                card
                            )
                            assignees_text = " - %s" % assignees if assignees else ""

                            # Add long-running indicator
                            long_running = (
                                "🐌 "
                                if self.is_card_long_running(
                                    board_id, card["id"], card_states
                                )
                                else ""
                            )

                            report_parts.append(
                                "• %s%s%s" % (long_running, card_link, assignees_text)
                            )

            except Exception as e:
                report_parts.append(
                    "\n❌ Error getting data for board %s: %s" % (board_id, str(e))
                )

        # Summary
        if total_overdue == 0 and total_current == 0:
            report_parts.append("\n✅ All tasks completed on time!")
        else:
            summary = "\n📈 <b>Summary:</b>"
            if total_overdue > 0:
                summary += "\n• Overdue: %d" % total_overdue
            if total_current > 0:
                summary += "\n• Current: %d" % total_current
            report_parts.append(summary)

        return "\n".join(report_parts)

    async def generate_weekly_stats_report(self) -> str:
        """Generate weekly statistics report with completed tasks list"""
        report_parts = ["📈 <b>Weekly Trello Statistics</b>\n"]

        # Get date range for last week
        today = datetime.now()
        week_start = today - timedelta(days=7)

        total_completed = 0
        total_overdue = 0
        all_completed_tasks = []  # List of all completed tasks for detailed view

        for board_id in config.board_ids:
            try:
                # Get all data including archived cards in parallel
                board_info_task = self.trello.get_board_info(board_id)
                all_cards_task = self.trello.get_all_board_cards_including_archived(
                    board_id
                )
                lists_task = self.trello.get_board_lists(board_id)

                # Wait for all data
                board_info, all_cards, lists = await asyncio.gather(
                    board_info_task, all_cards_task, lists_task
                )

                board_name = board_info["name"]
                list_names = {lst["id"]: lst["name"] for lst in lists}

                # Count completed cards from last week
                completed_this_week = []
                for card in all_cards:
                    list_name = list_names.get(card["idList"], "")
                    is_done = any(
                        done_name.lower() in list_name.lower()
                        for done_name in config.done_list_names
                    )

                    if is_done and card.get("dateLastActivity"):
                        # Check if completed in the last week
                        try:
                            last_activity = datetime.fromisoformat(
                                card["dateLastActivity"].replace("Z", "+00:00")
                            ).replace(tzinfo=None)

                            if last_activity >= week_start:
                                completed_this_week.append(
                                    {
                                        "name": card["name"],
                                        "url": card["shortUrl"],
                                        "board": board_name,
                                        "list": list_name,
                                        "completed_date": last_activity,
                                    }
                                )
                        except (ValueError, TypeError):
                            continue

                # Count current overdue cards (only from active cards)
                active_cards = await self.trello.get_board_cards(board_id)
                overdue_cards = [
                    card
                    for card in active_cards
                    if self.trello.is_card_overdue(card)
                    and not self._is_card_done(card, list_names)
                ]

                total_completed += len(completed_this_week)
                total_overdue += len(overdue_cards)
                all_completed_tasks.extend(completed_this_week)

                # Add board statistics
                if completed_this_week or overdue_cards:
                    report_parts.append("🗂️ <b>%s</b>" % board_name)
                    report_parts.append(
                        "✅ Completed this week: %d" % len(completed_this_week)
                    )
                    report_parts.append("⏰ Currently overdue: %d" % len(overdue_cards))

            except Exception as e:
                report_parts.append(
                    "\n❌ Error getting data for board %s: %s" % (board_id, str(e))
                )

        # Weekly summary
        report_parts.append("\n📊 <b>Overall Statistics:</b>")
        report_parts.append("✅ Total completed this week: %d" % total_completed)
        report_parts.append("⏰ Total overdue: %d" % total_overdue)

        # Add detailed list of completed tasks
        if all_completed_tasks:
            report_parts.append("\n📋 <b>Completed tasks this week:</b>")

            # Sort by completion date (newest first)
            all_completed_tasks.sort(key=lambda x: x["completed_date"], reverse=True)

            for task in all_completed_tasks:
                completed_date = task["completed_date"].strftime("%d.%m")

                report_parts.append(
                    "• <a href='%s'>%s</a>" % (task["url"], task["name"])
                )
                report_parts.append("  📅 %s | 📋 %s" % (completed_date, task["board"]))

        return "\n".join(report_parts)
