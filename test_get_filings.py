import os
import json
from datetime import datetime, timedelta
from sec_edgar_api import EdgarClient
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import httpx
import warnings

# URL for the SEC's ticker to CIK mapping file
CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

def get_cik_map():
    """
    Downloads the ticker-to-CIK mapping from the SEC and returns it as a dictionary.
    """
    headers = {'User-Agent': 'Your Name <adsddtion@gmail.com>'}
    response = httpx.get(CIK_MAP_URL, headers=headers)
    response.raise_for_status()
    all_companies = response.json()
    # The JSON is a dictionary of dictionaries, so we iterate over the values
    # and create a new dictionary mapping ticker to CIK
    return {company['ticker']: company['cik_str'] for company in all_companies.values()}

def get_latest_filings(ticker: str, years: int = 3):
    """
    Fetches the latest 10-K and 10-Q filings for a given ticker over a specified number of years.

    Args:
        ticker (str): The stock ticker symbol.
        years (int): The number of years to look back for filings.
    """
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    edgar = EdgarClient(user_agent="Your Name <adsddtion@gmail.com>")
    
    # Create a directory to save the filings
    if not os.path.exists(ticker):
        os.makedirs(ticker)

    # Define the date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365)

    print(f"Fetching filings for {ticker} from {start_date.date()} to {end_date.date()}...")

    try:
        print("Fetching CIK for ticker...")
        ticker_map = get_cik_map()
        cik = ticker_map.get(ticker.upper())

        if not cik:
            print(f"Ticker {ticker} not found.")
            return

        print(f"Found CIK: {cik}")
        
        # Get all submissions for the CIK. The CIK must be a 10-digit string.
        submissions = edgar.get_submissions(cik=str(cik).zfill(10))
        
        # The API returns data in a columnar format. We need to transpose it.
        recent = submissions.get('filings', {}).get('recent', {})
        
        # Check if there's any data
        if not recent or 'form' not in recent:
            print(f"No recent filings found for {ticker}.")
            return

        # Create a list of filing dictionaries by transposing the columnar data
        all_filings = []
        forms = recent.get('form', [])
        accession_numbers = recent.get('accessionNumber', [])
        filing_dates = recent.get('filingDate', [])
        primary_documents = recent.get('primaryDocument', [])
        
        for i in range(len(forms)):
            form_type = forms[i]
            if form_type in ['10-K', '10-Q']:
                all_filings.append({
                    'form': form_type,
                    'accessionNumber': accession_numbers[i],
                    'filingDate': filing_dates[i],
                    'primaryDocument': primary_documents[i],
                })

        # Filter filings within the date range
        recent_filings = [
            f for f in all_filings
            if start_date.date() <= datetime.strptime(f['filingDate'], '%Y-%m-%d').date() <= end_date.date()
        ]

        if not recent_filings:
            print(f"No 10-K or 10-Q filings found for {ticker} in the last {years} years.")
            return

        print(f"Found {len(recent_filings)} filings. Downloading and extracting text...")

        for filing in recent_filings:
            # Construct the filing URL
            accession_no_no_dashes = filing['accessionNumber'].replace('-', '')
            primary_doc = filing['primaryDocument']
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_no_dashes}/{primary_doc}"

            form_type = filing['form']
            filing_date = filing['filingDate']
            
            # Create a unique filename
            filename = f"{ticker}/{ticker}_{form_type.replace('/', '_')}_{filing_date}.txt"

            try:
                # Download the filing document
                response = httpx.get(filing_url, headers={"User-Agent": "Your Name <your_email@example.com>"})
                response.raise_for_status()
                
                # Parse the HTML and extract text
                soup = BeautifulSoup(response.content, 'lxml')
                
                # Try to find the document text, which is often in a <TEXT> tag
                document_tag = soup.find('document')
                if document_tag:
                    filing_text = document_tag.get_text(separator='\\n', strip=True)
                else:
                    filing_text = soup.get_text(separator='\\n', strip=True)

                # Save the text to a file
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(filing_text)
                
                print(f"Successfully saved {filename}")

            except httpx.HTTPStatusError as e:
                print(f"Failed to download {filing_url}: {e}")
            except Exception as e:
                print(f"An error occurred while processing {filing_url}: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    # Example usage:
    ticker_symbol = input("Enter the ticker symbol (e.g., AAPL): ")
    if ticker_symbol:
        get_latest_filings(ticker_symbol) 