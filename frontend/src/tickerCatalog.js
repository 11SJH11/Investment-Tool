// tickerCatalog.js
//
// A curated starting list for the ticker picker dropdown. Not exhaustive --
// you can always type a custom ticker too. Organized so bonds, commodities,
// and futures are clearly separated from stocks, since they carry different
// risk profiles.

export const TICKER_CATALOG = {
  "Stocks — Technology": [
    { ticker: "AAPL", name: "Apple" },
    { ticker: "MSFT", name: "Microsoft" },
    { ticker: "NVDA", name: "Nvidia" },
    { ticker: "GOOGL", name: "Alphabet" },
    { ticker: "AMZN", name: "Amazon" },
  ],
  "Stocks — Healthcare": [
    { ticker: "JNJ", name: "Johnson & Johnson" },
    { ticker: "UNH", name: "UnitedHealth" },
    { ticker: "PFE", name: "Pfizer" },
    { ticker: "ABBV", name: "AbbVie" },
  ],
  "Stocks — Financial Services": [
    { ticker: "JPM", name: "JPMorgan Chase" },
    { ticker: "BAC", name: "Bank of America" },
    { ticker: "GS", name: "Goldman Sachs" },
    { ticker: "V", name: "Visa" },
  ],
  "Stocks — Consumer Defensive": [
    { ticker: "PG", name: "Procter & Gamble" },
    { ticker: "KO", name: "Coca-Cola" },
    { ticker: "WMT", name: "Walmart" },
    { ticker: "COST", name: "Costco" },
  ],
  "Stocks — Consumer Cyclical": [
    { ticker: "TSLA", name: "Tesla" },
    { ticker: "HD", name: "Home Depot" },
    { ticker: "NKE", name: "Nike" },
    { ticker: "MCD", name: "McDonald's" },
  ],
  "Stocks — Energy": [
    { ticker: "XOM", name: "ExxonMobil" },
    { ticker: "CVX", name: "Chevron" },
  ],
  "Stocks — Industrials": [
    { ticker: "CAT", name: "Caterpillar" },
    { ticker: "BA", name: "Boeing" },
    { ticker: "HON", name: "Honeywell" },
  ],
  "Stocks — Utilities": [
    { ticker: "NEE", name: "NextEra Energy" },
    { ticker: "DUK", name: "Duke Energy" },
  ],
  "Stocks — Real Estate": [
    { ticker: "PLD", name: "Prologis" },
    { ticker: "AMT", name: "American Tower" },
  ],
  "Bonds (ETFs)": [
    { ticker: "BND", name: "Vanguard Total Bond Market" },
    { ticker: "AGG", name: "iShares Core US Aggregate Bond" },
    { ticker: "TLT", name: "iShares 20+ Year Treasury" },
    { ticker: "IEF", name: "iShares 7-10 Year Treasury" },
    { ticker: "SHY", name: "iShares 1-3 Year Treasury" },
    { ticker: "LQD", name: "iShares Investment Grade Corporate" },
    { ticker: "HYG", name: "iShares High Yield Corporate" },
    { ticker: "TIP", name: "iShares TIPS (Inflation-Protected)" },
  ],
  "Commodities (ETFs)": [
    { ticker: "GLD", name: "SPDR Gold Shares" },
    { ticker: "SLV", name: "iShares Silver" },
    { ticker: "DBC", name: "Invesco DB Commodity Index" },
    { ticker: "USO", name: "United States Oil Fund" },
    { ticker: "UNG", name: "United States Natural Gas Fund" },
  ],
  "Futures — leveraged, expire, higher risk": [
    { ticker: "ES=F", name: "S&P 500 Futures" },
    { ticker: "GC=F", name: "Gold Futures" },
    { ticker: "CL=F", name: "Crude Oil Futures" },
    { ticker: "NG=F", name: "Natural Gas Futures" },
    { ticker: "ZN=F", name: "10-Year Treasury Note Futures" },
  ],
  "Broad Market Benchmarks": [
    { ticker: "VOO", name: "Vanguard S&P 500" },
    { ticker: "SPY", name: "SPDR S&P 500" },
    { ticker: "VTI", name: "Vanguard Total US Market" },
    { ticker: "QQQ", name: "Invesco Nasdaq-100" },
    { ticker: "DIA", name: "SPDR Dow Jones" },
    { ticker: "IWM", name: "iShares Russell 2000 (small-cap)" },
    { ticker: "VXUS", name: "Vanguard Total International" },
  ],
  Crypto: [
    { ticker: "BTC-USD", name: "Bitcoin" },
    { ticker: "ETH-USD", name: "Ethereum" },
  ],
};
