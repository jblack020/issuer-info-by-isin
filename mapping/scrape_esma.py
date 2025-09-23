import asyncio
import contextlib
from typing import Dict, List, Optional
import pandas as pd
from tqdm import tqdm
from playwright.async_api import async_playwright

# Knobs & Constants
ISIN_INPUT_FILE = "isins/SampleKeys.xlsx"
ESMA_LEI_ISIN_FILE = "mapping/dbs/esma_lei_isin.csv"
TIMEOUTS = {
    "page_load": 60000,
    "search_load": 1000,
    "results_load": 15000,
    "error": 10000,
    "between_pages": 250
}

NUM_WORKERS = 3
HEADLESS = True
ESMA_URL = "https://registers.esma.europa.eu/publication/searchRegister?core=esma_registers_firds"

async def scrape_esma_for_isins(isins: List[str], num_workers: int) -> Dict[str, Optional[str]]:
    """Scrape ESMA FIRDS for a list of ISINs and return a mapping of ISIN -> LEI (or None).

    Uses a small pool of pages (workers) in one browser for concurrency.
    """
    url = ESMA_URL
    results: Dict[str, Optional[str]] = {}

    async def lookup_on_page(page, isin: str) -> Optional[str]:
        # Clear and fill input
        await page.fill('input[name="isin"]', "")
        await page.fill('input[name="isin"]', isin)

        # Submit search
        await page.click("#searchSolrButton")

        # Give the page a brief moment to start updating
        await page.wait_for_timeout(TIMEOUTS["search_load"])

        # Define locators
        no_data_locator = page.locator("#noData")  # check exact ID spelling!
        lei_cell_locator = page.locator("#T01 tbody tr:first-child td:nth-child(5)")

        # Wait for either locator to appear
        done, pending = await asyncio.wait(
            [
                asyncio.create_task(no_data_locator.wait_for(state="visible", timeout=TIMEOUTS["results_load"])),
                asyncio.create_task(lei_cell_locator.wait_for(state="visible", timeout=TIMEOUTS["results_load"])),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # Ensure we don't leak exceptions from background tasks
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        for task in done:
            with contextlib.suppress(Exception):
                _ = task.result()

        if await no_data_locator.is_visible():
            return None

        if await lei_cell_locator.is_visible():
            lei_text = None
            row_index = 1
            while lei_text is None or lei_text.strip() == "":
                current_row_locator = page.locator(f"#T01 tbody tr:nth-child({row_index}) td:nth-child(5)")
                if not await current_row_locator.is_visible():
                    break
                lei_text = await current_row_locator.inner_text()
                if lei_text and lei_text.strip():
                    break
                row_index += 1
            return lei_text.strip() if lei_text else None

        # Fallback
        return None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"])
        context = await browser.new_context()

        # Block images, stylesheets, fonts and media to speed up
        async def route_interceptor(route):
            request = route.request
            if request.resource_type in {"image", "stylesheet", "font", "media"}:
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", route_interceptor)

        queue: asyncio.Queue[str] = asyncio.Queue()
        for code in isins:
            queue.put_nowait(str(code))

        # Progress bar for per-ISIN progress across workers
        pbar = tqdm(total=len(isins), desc="ESMA lookups", unit="isin")
        progress_lock = asyncio.Lock()

        async def worker(worker_id: int):
            page = await context.new_page()
            await page.goto(url, timeout=TIMEOUTS["page_load"])
            while True:
                try:
                    isin = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    lei = await lookup_on_page(page, isin)
                    results[isin] = lei
                except Exception as e:
                    print(f"[EXCEPTION] Error handling ISIN {isin}: {e}")
                    results[isin] = None
                finally:
                    # Safely advance the progress bar from concurrent workers
                    async with progress_lock:
                        pbar.update(1)
                await page.wait_for_timeout(TIMEOUTS["between_pages"])  # brief pause to be polite
            await page.close()

        workers = [asyncio.create_task(worker(i)) for i in range(max(1, int(NUM_WORKERS)))]
        await asyncio.gather(*workers)
        await browser.close()
        pbar.close()

    return results


def fetch_esma_mappings_for_isins(isins: List[str], num_workers: int = NUM_WORKERS) -> Dict[str, Optional[str]]:
    """Synchronous helper to fetch ESMA FIRDS mappings for a list of ISINs.

    Returns a dict of ISIN -> LEI (or None if not found).
    """
    if not isins:
        return {}
    # Deduplicate while preserving order
    seen = set()
    unique_isins: List[str] = []
    for code in isins:
        if code not in seen:
            seen.add(code)
            unique_isins.append(str(code))
    return asyncio.run(scrape_esma_for_isins(unique_isins, num_workers=num_workers))