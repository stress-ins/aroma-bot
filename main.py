import asyncio
import logging

from bot.application import build_application
from bot.services.brand_settings_store import preload_brand_settings
from scheduler.jobs import setup_scheduler

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    app = build_application()
    scheduler = setup_scheduler(app)

    await preload_brand_settings()
    scheduler.start()
    logger.info("Scheduler started")

    logger.info("Bot starting...")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running. Press Ctrl+C to stop.")
        try:
            from bot.handlers.monitor import notify_owner
            notify_owner("✅ <b>aroma-bot запущен</b>")
        except Exception:
            pass
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await app.updater.stop()
            await app.stop()
            scheduler.shutdown()
            logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
