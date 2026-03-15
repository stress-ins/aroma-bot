import asyncio
import logging

from bot.application import build_application
from bot.services.brand_settings_store import preload_brand_settings
from bot.services.scheduler import run_loop as scheduler_run_loop

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    app = build_application()

    await preload_brand_settings()

    logger.info("Bot starting...")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running. Press Ctrl+C to stop.")

        scheduler_task = asyncio.create_task(scheduler_run_loop(app))

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
            scheduler_task.cancel()
            await app.updater.stop()
            await app.stop()
            logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
