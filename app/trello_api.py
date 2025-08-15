import asyncio
import logging
from datetime import datetime
from typing import List, Optional

import aiohttp

from app import config

# Initialize logging


class AsyncTrelloAPI:
    def __init__(self):
        self.api_key = config.TRELLO_API_KEY
        self.token = config.TRELLO_TOKEN
        self.base_url = "https://api.trello.com/1"
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def _ensure_session(self):
        """Ensure session is available"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Make authenticated request to Trello API"""
        await self._ensure_session()

        url = f"{self.base_url}/{endpoint}"
        default_params = {"key": self.api_key, "token": self.token}
        if params:
            default_params.update(params)

        try:
            async with self.session.get(
                url, params=default_params, timeout=30
            ) as response:
                # Better error handling
                if response.status == 401:
                    logging.error("401 Unauthorized - Check API key and token")
                    logging.error("API Key: %s...", self.api_key[:10])
                    logging.error("Token: %s...", self.token[:10])
                    logging.error("URL: %s", url)

                    # Test basic auth
                    test_url = f"{self.base_url}/members/me"
                    async with self.session.get(
                        test_url, params={"key": self.api_key, "token": self.token}
                    ) as test_response:
                        if test_response.status == 200:
                            logging.info(
                                "Authentication works, possible board access issue"
                            )
                        else:
                            logging.error("Authentication problem")

                elif response.status == 404:
                    logging.error("404 Not Found - Board not found: %s", endpoint)

                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as e:
            logging.error("Request error: %s", e)
            raise
        except asyncio.TimeoutError as e:
            logging.error("Request timeout: %s", e)
            raise

    async def test_authentication(self) -> bool:
        """Test if authentication works"""
        try:
            result = await self._make_request("members/me")
            logging.info(
                "Authentication successful. User: %s", result.get("username", "Unknown")
            )
            return True
        except Exception as e:
            logging.error("Authentication error: %s", e)
            return False

    async def get_board_info(self, board_id: str) -> dict:
        """Get board information"""
        return await self._make_request(f"boards/{board_id}")

    async def get_board_cards(self, board_id: str) -> List[dict]:
        """Get all cards from a board"""
        return await self._make_request(
            f"boards/{board_id}/cards", {"members": "true", "due": "true"}
        )

    async def get_all_board_cards_including_archived(self, board_id: str) -> List[dict]:
        """Get all cards from a board including archived ones"""
        return await self._make_request(
            f"boards/{board_id}/cards",
            {"members": "true", "due": "true", "filter": "all"},
        )

    async def get_board_lists(self, board_id: str) -> List[dict]:
        """Get all lists from a board"""
        return await self._make_request(f"boards/{board_id}/lists")

    async def get_card_members(self, card_id: str) -> List[dict]:
        """Get members assigned to a card"""
        return await self._make_request(f"cards/{card_id}/members")

    def is_card_overdue(self, card: dict) -> bool:
        """Check if card is overdue"""
        if not card.get("due"):
            return False

        due_date = datetime.fromisoformat(card["due"].replace("Z", "+00:00"))
        return datetime.now(due_date.tzinfo) > due_date

    async def get_overdue_cards(self, board_id: str) -> List[dict]:
        """Get all overdue cards from a board"""
        cards = await self.get_board_cards(board_id)
        return [card for card in cards if self.is_card_overdue(card)]

    async def get_cards_in_progress(self, board_id: str) -> List[dict]:
        """Get cards that are in progress"""
        cards = await self.get_board_cards(board_id)
        lists = await self.get_board_lists(board_id)

        # Create mapping of list IDs to names
        list_names = {lst["id"]: lst["name"] for lst in lists}

        in_progress_cards = []
        for card in cards:
            list_name = list_names.get(card["idList"], "")
            if any(
                name.lower() in list_name.lower()
                for name in config.in_progress_list_names
            ):
                in_progress_cards.append(card)

        return in_progress_cards

    def get_card_assignees_as_telegram_tags(self, card: dict) -> str:
        """Get card assignees as Telegram tags"""
        if not card.get("members"):
            return ""

        tags = []
        for member in card["members"]:
            username = member.get("username", "")
            telegram_tag = config.trello_to_telegram_users.get(username, f"@{username}")
            tags.append(telegram_tag)

        return " ".join(tags)

    def format_card_link(self, card: dict) -> str:
        """Format card as clickable link"""
        return f'<a href="{card["shortUrl"]}">{card["name"]}</a>'

    async def get_current_cards(self, board_id: str) -> List[dict]:
        """Get cards that are currently active (started but not overdue)"""
        cards = await self.get_board_cards(board_id)
        current_cards = []
        now = datetime.now()

        for card in cards:
            # Skip if card is overdue
            if self.is_card_overdue(card):
                continue

            start_date = card.get("start")
            due_date = card.get("due")

            # Check if card should be current
            is_current = False

            if start_date:
                # Parse start date
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                start_dt = start_dt.replace(
                    tzinfo=None
                )  # Remove timezone for comparison

                # Card started
                if start_dt <= now:
                    if due_date:
                        # Has due date - check if not expired
                        due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                        due_dt = due_dt.replace(tzinfo=None)
                        if due_dt > now:
                            is_current = True
                    else:
                        # No due date - consider current if started
                        is_current = True
            elif not start_date and not due_date:
                # No dates - use list-based logic as fallback
                lists = await self.get_board_lists(board_id)
                list_names = {lst["id"]: lst["name"] for lst in lists}
                list_name = list_names.get(card["idList"], "")

                if any(
                    name.lower() in list_name.lower()
                    for name in config.in_progress_list_names
                ):
                    is_current = True

            if is_current:
                current_cards.append(card)

        return current_cards

    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()


# For backward compatibility, keep the old class name as an alias
TrelloAPI = AsyncTrelloAPI
