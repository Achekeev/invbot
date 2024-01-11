#!/usr/bin/env python3

import logging
import asyncio
from invbot.db.models import create_all

async def main():
    logging.info('init db')
    await create_all()

asyncio.run(main())


