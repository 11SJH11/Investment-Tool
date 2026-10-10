export const BROKER_NAMES = {robinhood:'Robinhood',oanda:'OANDA', trading212:'Trading 212', tradelocker:'TradeLocker', mt5:'MetaTrader 5', tradovate:'Tradovate'};
export const canConfigureConnection = provider => ['trading212','tradelocker','mt5','robinhood'].includes(provider);
export const canSelectAccount = provider => ['tradelocker','mt5','robinhood'].includes(provider);
export const connectionSummary = profile => profile.disconnected ? 'Disconnected' : profile.configured ? 'Configured' : 'Not configured';
export const connectionHint = provider => provider === 'robinhood' ? 'Official Robinhood Trading MCP read access. Configure backend OAuth authorization, test the connection, then select an account. Portfolio viewing never enables Ledger order execution.' : provider === 'mt5'
  ? 'Install the optional official MetaTrader5 Python package and run a logged-in MetaTrader 5 terminal on the machine hosting Ledger. MT4 is not supported.'
  : provider === 'tradelocker' ? 'Configure TradeLocker credentials on the backend, choose demo/live, test the connection, then select an account. Historical order aggregates may have unavailable costs/P&L.'
  : 'Configure credentials on the backend. Only read permissions are needed.';
