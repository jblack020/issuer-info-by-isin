# issuer-info-by-isin

## Quick start

### (1) Requirements

- Python 3.10+ recommended
- macOS (tested), should also work on Linux/Windows

Install Python deps and Playwright browsers:
`python3 -m venv .venv && source .venv/bin/activate`
pip install -r requirements.txt
python -m playwright install chromium```

### (2) Upload ISINs of interest

As of right now, the script pulls ISINs of interest from "isins/SampleKeys.xlsx." If you wish to pull information about issuers of different securities, upload the file as an Excel sheet to the 'isins/' folder. It MUST have one column named "isin", where the ISINs are stored — other columns (e.g., issuer) are fine but not required.

### (3) Run "main.py" using the following command

`python3 main.py --isins-file-name {FILE_NAME}`,
where {FILE_NAME} is the name of the file that contains your ISIN keys, which should be placed in the "isins" folder (see above).

e.g.,
`python3 main.py --isins-file-name keys.xlsx`,
`python3 main.py --isins-file-name sample.xlsx`,

--isins-file-name will default to "SampleKeys.xlsx", which is a file of 90 sample ISINs.

    Note three other optional CLI flags:
        --fresh
        Setting --fresh will delete the current cache, which will cause the ESMA scraper to re-run for all ISINs not covered by the GLEIN dataset.

        --force-retry
        When linking ISINs to LEIs, the script first checks the cache to see if we have already tried to link any given ISIN in a previous run of the script. For instance, if we've already linked ISIN "US123456" → LEI "87654321", the script will skip looking in GLEIF or scraping ESMA for that ISIN, and will instead use the cached LEI (even if the cached LEI is blank).

        Setting --force-retry means that if an ISIN appears in the cache but is linked to a blank LEI (i.e., we've already tried to lookup an LEI for this ISIN in ESMA and GLEIF, but found nothing), we'll treat that ISIN as if it had never been cached and try to find a corresponding LEI in GLEIF and ESMA.

        --skip-final-merge
        The default behavior of the script is to provide a list of LEIs, which the user will then mass-upload to Orbis to retrieve the information about each issuer that they wish to see (e.g., sales, assets, etc) as an Excel file. Then, the user uploads the Excel file from Orbis to a folder named 'temp' and presses enter to continue. The script then merges the Orbis data with the ISINs of interest, created a dataset of:

        ISIN -- LEI -- {Other relevant information about issuer from Orbis}

        To skip this behavior (e.g., if you don't care about the linking the corporate information to the ISINs you uploaded, or will do it on your own) then set --skip-final-merge.
