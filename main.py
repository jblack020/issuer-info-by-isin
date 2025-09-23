import pandas as pd
import os
from typing import List
from mapping.map import isins_to_leis, MAPPING_CACHE_FILE
import argparse
import glob
import shutil
import hashlib
from datetime import datetime
import re

RESULTS_FOLDER = 'results'
TEMP_FOLDER = 'temp'

# Simple ANSI styling helpers
class Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    GREEN = "\033[32m"
    ORANGE = "\033[38;5;208m"

def style(text: str, *codes: str) -> str:
    return "".join(codes) + text + Ansi.RESET

def sanitize_component(text: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', str(text)).strip('_')
    return safe or "file"

def build_unique_merged_path(results_dir: str, source_excel_path: str, df: pd.DataFrame) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    source_base = os.path.splitext(os.path.basename(source_excel_path))[0]
    source_part = sanitize_component(source_base)[:50]
    rows = len(df)
    try:
        payload = df.to_csv(index=False).encode("utf-8")
        short_hash = hashlib.sha1(payload).hexdigest()[:8]
    except Exception:
        short_hash = hashlib.sha1(f"{rows}|{source_part}|{timestamp}".encode("utf-8")).hexdigest()[:8]
    filename = f"merged_{timestamp}_{source_part}_{rows}rows_{short_hash}.csv"
    return os.path.join(results_dir, filename)

def get_keys(file_path) -> List[str]:
    """Read ISINs from the sample isins file (column 'ISIN Keys')."""
    try:
        sample_isins = pd.read_excel(file_path, header=0)['isin'].dropna().astype(str).str.strip().tolist()
    except Exception:
        print(f"Error reading the file {file_path}. Please ensure the file is in the 'isins' folder and is a valid Excel file. Do not include the 'isins' folder in the file name.")
        exit(1)
    return sample_isins

def print_next_steps(skip_final_merge: bool):
    """Print the next steps to the user with ANSI colors and bold."""
    header = "Next steps"
    print(style("\n" + header, Ansi.BOLD, Ansi.YELLOW))
    steps = [
        "Copy the LEIs that will be listed below",
        "Navigate to the following URL while logged into Orbis: \nhttps://orbis-r1.bvdinfo.com/version-20250619-3-0/Orbis/1/Companies/Search/By/LegalEntityIdentifier",
        "Paste the LEIs into the input form",
        "Click 'Search', then 'View Results'",
        "Add relevant columns (e.g., total assets, sales, operating revenue). \n**NOTE: LEI (Legal Entity Identifier) must be included as one of the columns.**",
        "Export as Excel",
    ]
    if not skip_final_merge:
        steps.append("Move the downloaded Excel file to the 'temp' folder")
    for idx, step in enumerate(steps, 1):
        print(f"{style(str(idx) + '.', Ansi.BOLD, Ansi.YELLOW)} {step}")
    print(style("\n\nPress enter to receive the LEIs to copy", Ansi.BOLD, Ansi.YELLOW))
    input()
    
def print_leis_to_copy(leis: List[str]):
    """Print the LEIs to copy to the user with ANSI colors and bold."""
    for lei in leis:
        print(style(str(lei), Ansi.GREEN))
    print()
    
def reset_cache():
    """Reset the cache by deleting the cache file."""
    if os.path.exists(MAPPING_CACHE_FILE):
        os.remove(MAPPING_CACHE_FILE)
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Map ISINs to LEIs and process Orbis data")
    parser.add_argument("--force-retry", action="store_true", default=False, 
                       help="Force retry mapping for ISINs even if previously failed")
    parser.add_argument("--fresh", action="store_true", default=False,
                       help="Reset cache; retrieve all mappings fresh from GLEIF and ESMA")
    parser.add_argument("--skip-final-merge", action="store_true", default=False,
                       help="Perform final merge with downloaded data")
    parser.add_argument("--isins-file-name", type=str, default='SampleKeys.xlsx',
                       help="Name of the file containing the ISINs of interest, including the .xlsx extension. The file must be in the 'isins' folder.")
    args = parser.parse_args()  
    
    if args.isins_file_name == "SampleKeys.xlsx":
        print(style("Using the sample ISINs file. If you wish to use a different file, please provide the name of the file using the --isins-file-name flag.", Ansi.YELLOW))
    
    # Reset cache if --fresh is set
    if args.fresh:
        reset_cache()
    
    # Get the ISINs of interest
    isins = get_keys(f'isins/{args.isins_file_name.strip()}')
        
    # If no ISINs found, exit
    if len(isins) == 0:
        print(style("No ISINs found in the file provided.", Ansi.RED))
        exit(1)
    
    # Map the ISINs to LEIs, save the results to a dataframe 
    records = isins_to_leis(isins, force_retry=args.force_retry)
    mappings = pd.DataFrame(records)[['isin', 'lei']]
    
    # Print the next steps and the LEIs to copy
    print_next_steps(args.skip_final_merge)
    print_leis_to_copy(mappings['lei'].dropna())
    
    if not args.skip_final_merge:
        # Create a temporary folder to store the downloaded .xlsx file
        os.makedirs(TEMP_FOLDER, exist_ok=True)
        
        # Wait for the user to press enter
        print(style(f"Press enter when the downloaded .xlsx file is in the '{TEMP_FOLDER}' folder", Ansi.YELLOW))
        input()
        
        # Get whatever excel file is in the temp folder
        try:
            excel_file = glob.glob(f'{TEMP_FOLDER}/*.xlsx')[0]
        except Exception:
            print(style(f"No .xlsx file found in the '{TEMP_FOLDER}' folder. Please move the downloaded .xlsx file to the '{TEMP_FOLDER}' folder and try again.", Ansi.RED))
            shutil.rmtree(TEMP_FOLDER)
            exit(1)
        
        # Add any other columns to rename here:
        rename_map = {
            "LEI (Legal Entity Identifier)": 'lei'
        }

        # Read the excel file
        orbis_data = pd.read_excel(excel_file, sheet_name="Results", header=0).rename(columns=rename_map)
        
        # Merge it by LEI with the ISINs 
        merged = pd.merge(mappings, orbis_data, on='lei', how='left')
        merged = merged.drop(columns=[col for col in merged.columns if col.startswith('Unnamed')], errors='ignore')
        
        # Save the merged dataframe to a uniquely named CSV file
        output_path = build_unique_merged_path(RESULTS_FOLDER, excel_file, merged)
        merged.to_csv(output_path, index=False)
        
        print(style(f"Merged dataframe saved to '{output_path}'", Ansi.GREEN))
        
        # Remove temp folder
        shutil.rmtree(TEMP_FOLDER)