import asyncio
import logging
import signal
import sys
import traceback

from app import config
from app.bot import AsyncTrelloBot
from app.logger import setup_logging
from app.scheduler import Scheduler

# Global bot instance
bot_instance = None
scheduler = None


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logging.info("Received signal %d. Shutting down gracefully...", signum)
    sys.exit(0)


async def start_polling():
    """Start bot polling in background"""
    try:
        await bot_instance.dp.start_polling(bot_instance.bot)
    except Exception as e:
        logging.error("Error in polling: %s", e)


async def run_bot():
    """Main async bot function"""
    global bot_instance, scheduler

    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async with AsyncTrelloBot() as bot:
        bot_instance = bot

        # Initialize scheduler
        scheduler = Scheduler(bot_instance)

        # Get bot information
        print("🤖 Getting bot information...")
        if not await bot.get_bot_info():
            print("⚠️ Failed to get bot information")

        # Setup bot commands
        print("📋 Registering bot commands...")
        if not await bot.setup_bot_commands():
            print("⚠️ Failed to register bot commands")

        # Test Trello authentication
        print("🔍 Testing Trello connection...")
        if not await bot.trello.test_authentication():
            print("❌ Failed to connect to Trello. Check settings in config.py")
            return

        # Test board access
        print("🔍 Testing board access...")
        for i, board_id in enumerate(config.board_ids):
            try:
                board_info = await bot.trello.get_board_info(board_id)
                print(
                    "✅ Board %d: %s (ID: %s)" % (i + 1, board_info["name"], board_id)
                )
            except Exception as e:
                print("❌ Error accessing board %s: %s" % (board_id, e))

        # Setup scheduled tasks
        scheduler.setup_schedule()

        logging.info("🤖 Async Trello Bot started...")
        logging.info("Monitoring %d boards", len(config.board_ids))
        logging.info("Check interval: %d seconds", config.DELAY)

        # Start polling in background
        polling_task = asyncio.create_task(start_polling())

        try:
            # Main async loop
            while True:
                # Check for completed cards and member changes
                await bot.check_for_completed_cards()

                # Run scheduled tasks
                scheduler.run_pending()

                # Wait for next check
                await asyncio.sleep(config.DELAY)

        except KeyboardInterrupt:
            logging.info("Bot stopped by user")
        except Exception as e:
            logging.error("Unexpected error: %s", e)
            logging.error(traceback.format_exc())
        finally:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run_bot())
