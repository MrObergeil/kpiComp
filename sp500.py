"""
S&P 500 tickers organized by sector.
Source: Yahoo Finance sector data (as of Feb 2026).
Used to find sector peers for comparison without fetching all 500 tickers.
"""

SP500_BY_SECTOR = {
    "Basic Materials": [
        "ALB", "APD", "CE", "CF", "CTVA", "DD", "DOW", "ECL", "EMN", "FCX",
        "FMC", "IFF", "LIN", "LYB", "MLM", "MOS", "NEM", "NUE", "PPG", "SHW",
        "VMC",
    ],
    "Communication Services": [
        "CHTR", "CMCSA", "DIS", "EA", "FOX", "FOXA", "GOOG", "GOOGL", "LUMN",
        "LYV", "META", "MTCH", "NFLX", "NWS", "NWSA", "OMC", "T", "TMUS",
        "TTWO", "VZ", "WBD",
    ],
    "Consumer Cyclical": [
        "AMCR", "AMZN", "APTV", "AVY", "AZO", "BBWI", "BBY", "BKNG", "BWA",
        "CCL", "CMG", "CZR", "DHI", "DPZ", "DRI", "EBAY", "ETSY", "EXPE", "F",
        "GM", "GPC", "HAS", "HD", "IP", "KMX", "LEN", "LKQ", "LOW", "LVS",
        "MAR", "MCD", "MGM", "MHK", "NCLH", "NKE", "NVR", "ORLY", "PHM", "PKG",
        "PVH", "RCL", "RL", "ROL", "ROST", "SBUX", "SEE", "TJX", "TPR", "TSCO",
        "TSLA", "ULTA", "VFC", "WHR", "WYNN", "YUM",
    ],
    "Consumer Defensive": [
        "ADM", "CAG", "CHD", "CL", "CLX", "COST", "CPB", "DG", "DLTR", "EL",
        "GIS", "HRL", "HSY", "KDP", "KHC", "KMB", "KO", "KR", "LW", "MDLZ",
        "MKC", "MNST", "MO", "NWL", "PEP", "PG", "PM", "SJM", "STZ", "SYY",
        "TAP", "TGT", "TSN", "WMT",
    ],
    "Energy": [
        "APA", "BKR", "COP", "CTRA", "CVX", "DVN", "EOG", "EQT", "FANG", "HAL",
        "KMI", "MPC", "OKE", "OXY", "PSX", "SLB", "TRGP", "VLO", "WMB", "XOM",
    ],
    "Financial Services": [
        "AFL", "AIG", "AIZ", "AJG", "ALL", "AMP", "AON", "AXP", "BAC", "BEN",
        "BK", "BLK", "BRO", "C", "CB", "CBOE", "CFG", "CINF", "CMA", "CME",
        "COF", "FDS", "FITB", "GL", "GS", "HBAN", "ICE", "IVZ", "JPM", "KEY",
        "L", "LNC", "MA", "MCO", "MET", "MKTX", "MMC", "MS", "MSCI", "MTB",
        "NDAQ", "NTRS", "PFG", "PGR", "PNC", "PRU", "PYPL", "RF", "RJF", "SBNY",
        "SCHW", "SPGI", "STT", "SYF", "TFC", "TROW", "TRV", "USB", "V", "WFC",
        "WRB", "WTW", "ZION",
    ],
    "Healthcare": [
        "ABBV", "ABT", "ALGN", "AMGN", "BAX", "BDX", "BIIB", "BIO", "BMY",
        "BSX", "CAH", "CI", "CNC", "COO", "CRL", "CVS", "DGX", "DHR", "DVA",
        "DXCM", "EW", "GILD", "HCA", "HOLX", "HSIC", "HUM", "IDXX", "ILMN",
        "INCY", "IQV", "ISRG", "JNJ", "LH", "LLY", "MCK", "MDT", "MOH", "MRK",
        "MRNA", "MTD", "OGN", "PFE", "REGN", "RMD", "STE", "SYK", "TECH", "TFX",
        "TMO", "UHS", "UNH", "VRTX", "VTRS", "WAT", "WST", "XRAY", "ZBH", "ZTS",
    ],
    "Industrials": [
        "ALK", "ALLE", "AME", "AOS", "BA", "CARR", "CAT", "CHRW", "CMI", "CPRT",
        "CSX", "CTAS", "DAL", "DE", "DOV", "EFX", "EMR", "ETN", "EXPD", "FAST",
        "FDX", "GD", "GE", "GNRC", "GPN", "GWW", "HON", "HWM", "IEX", "IR",
        "ITW", "J", "JBHT", "JCI", "LHX", "LMT", "LUV", "MAS", "MMM", "NDSN",
        "NOC", "NSC", "ODFL", "OTIS", "PCAR", "PH", "PNR", "POOL", "PWR", "RHI",
        "ROK", "RSG", "RTX", "SNA", "SWK", "TDG", "TT", "TXT", "UAL", "UNP",
        "UPS", "URI", "VRSK", "WAB", "WM", "XYL",
    ],
    "Real Estate": [
        "AMT", "ARE", "AVB", "BXP", "CBRE", "CCI", "CPT", "CSGP", "DLR", "EQIX",
        "EQR", "ESS", "EXR", "FRT", "HST", "INVH", "IRM", "KIM", "MAA", "O",
        "PLD", "PSA", "REG", "SBAC", "SPG", "UDR", "VICI", "VNO", "VTR", "WELL",
        "WY",
    ],
    "Technology": [
        "AAPL", "ACN", "ADBE", "ADI", "ADP", "ADSK", "AKAM", "AMAT", "AMD",
        "ANET", "APH", "AVGO", "BR", "CDNS", "CDW", "CRM", "CSCO", "CTSH", "DXC",
        "ENPH", "EPAM", "FFIV", "FIS", "FTNT", "FTV", "GLW", "GRMN", "HPE",
        "HPQ", "IBM", "INTC", "INTU", "IT", "JKHY", "KEYS", "KLAC", "LDOS",
        "LRCX", "MCHP", "MPWR", "MSFT", "MSI", "MU", "NOW", "NTAP", "NVDA",
        "NXPI", "ON", "ORCL", "PAYC", "PAYX", "PTC", "QCOM", "QRVO", "ROP",
        "SNPS", "STX", "SWKS", "TDY", "TEL", "TER", "TRMB", "TXN", "TYL",
        "VRSN", "WDC", "ZBRA",
    ],
    "Utilities": [
        "AEE", "AEP", "AES", "ATO", "AWK", "CEG", "CMS", "CNP", "D", "DTE",
        "DUK", "ED", "EIX", "ES", "ETR", "EVRG", "EXC", "FE", "LNT", "NEE",
        "NI", "NRG", "PCG", "PEG", "PNW", "PPL", "SO", "SRE", "WEC", "XEL",
    ],
}

# Flat list for backward compatibility
SP500_TICKERS = [t for tickers in SP500_BY_SECTOR.values() for t in tickers]
