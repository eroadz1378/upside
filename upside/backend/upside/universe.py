"""Stocks the engine scans: large, liquid US names. Edit freely."""

UNIVERSE = [
    ("AAPL", "Apple", "Technology"), ("MSFT", "Microsoft", "Technology"),
    ("NVDA", "Nvidia", "Semiconductors"), ("AMZN", "Amazon.com", "Consumer / Cloud"),
    ("GOOGL", "Alphabet", "Communication"), ("META", "Meta Platforms", "Communication"),
    ("TSLA", "Tesla", "Consumer"), ("AVGO", "Broadcom", "Semiconductors"),
    ("AMD", "Advanced Micro Devices", "Semiconductors"), ("ORCL", "Oracle", "Software"),
    ("CRM", "Salesforce", "Software"), ("ADBE", "Adobe", "Software"),
    ("NFLX", "Netflix", "Communication"), ("INTC", "Intel", "Semiconductors"),
    ("QCOM", "Qualcomm", "Semiconductors"), ("CSCO", "Cisco", "Technology"),
    ("IBM", "IBM", "Technology"), ("NOW", "ServiceNow", "Software"),
    ("INTU", "Intuit", "Software"), ("PLTR", "Palantir", "Software"),
    ("SHOP", "Shopify", "Software"), ("UBER", "Uber", "Transportation"),
    ("MU", "Micron", "Semiconductors"), ("ANET", "Arista Networks", "Technology"),
    ("PANW", "Palo Alto Networks", "Cybersecurity"), ("CRWD", "CrowdStrike", "Cybersecurity"),
    ("JPM", "JPMorgan Chase", "Financials"), ("BAC", "Bank of America", "Financials"),
    ("GS", "Goldman Sachs", "Financials"), ("MS", "Morgan Stanley", "Financials"),
    ("V", "Visa", "Financials"), ("MA", "Mastercard", "Financials"),
    ("AXP", "American Express", "Financials"), ("LLY", "Eli Lilly", "Healthcare"),
    ("UNH", "UnitedHealth", "Healthcare"), ("JNJ", "Johnson & Johnson", "Healthcare"),
    ("MRK", "Merck", "Healthcare"), ("ABBV", "AbbVie", "Healthcare"),
    ("PFE", "Pfizer", "Healthcare"), ("TMO", "Thermo Fisher", "Healthcare"),
    ("ISRG", "Intuitive Surgical", "Healthcare"), ("AMGN", "Amgen", "Healthcare"),
    ("WMT", "Walmart", "Consumer Staples"), ("COST", "Costco", "Consumer Staples"),
    ("PG", "Procter & Gamble", "Consumer Staples"), ("KO", "Coca-Cola", "Consumer Staples"),
    ("PEP", "PepsiCo", "Consumer Staples"), ("MCD", "McDonald's", "Consumer"),
    ("NKE", "Nike", "Consumer"), ("HD", "Home Depot", "Consumer"),
    ("SBUX", "Starbucks", "Consumer"), ("DIS", "Disney", "Communication"),
    ("XOM", "Exxon Mobil", "Energy"), ("CVX", "Chevron", "Energy"),
    ("CAT", "Caterpillar", "Industrials"), ("GE", "GE Aerospace", "Industrials"),
    ("BA", "Boeing", "Industrials"), ("HON", "Honeywell", "Industrials"),
    ("UPS", "UPS", "Industrials"), ("RTX", "RTX", "Industrials"),
    ("DE", "Deere", "Industrials"),
]

TICKERS = [t for t, _, _ in UNIVERSE]
INFO = {t: {"name": n, "sector": s} for t, n, s in UNIVERSE}
