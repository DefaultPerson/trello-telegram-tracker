import asyncio
import logging

import schedule


class Scheduler:
    """Class for handling scheduled tasks"""

    def __init__(self, bot_instance):
        self.bot_instance = bot_instance

    async def scheduled_daily_report(self):
        """Scheduled daily report function"""
        if self.bot_instance:
            await self.bot_instance.send_daily_report()

    async def scheduled_weekly_report(self):
        """Scheduled weekly report function"""
        if self.bot_instance:
            await self.bot_instance.send_weekly_report()

    def schedule_daily_report(self):
        """Schedule daily report"""
        asyncio.create_task(self.scheduled_daily_report())

    def schedule_weekly_report(self):
        """Schedule weekly report"""
        asyncio.create_task(self.scheduled_weekly_report())

    def setup_schedule(self):
        """Setup all scheduled tasks"""
        schedule.every().monday.at("08:00").do(self.schedule_daily_report)
        schedule.every().tuesday.at("08:00").do(self.schedule_daily_report)
        schedule.every().wednesday.at("08:00").do(self.schedule_daily_report)
        schedule.every().thursday.at("08:00").do(self.schedule_daily_report)
        schedule.every().friday.at("08:00").do(self.schedule_daily_report)
        schedule.every().saturday.at("08:00").do(self.schedule_daily_report)
        schedule.every().monday.at("00:00").do(self.schedule_weekly_report)

        logging.info("Scheduled tasks configured")

    def run_pending(self):
        """Run pending scheduled tasks"""
        schedule.run_pending()
