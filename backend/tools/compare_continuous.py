"""Usage: python tools/compare_continuous.py ledger.csv tradingview.csv"""
import argparse
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.data.continuous_comparison import compare_exports

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger');parser.add_argument('reference')
    args=parser.parse_args()
    print(json.dumps(compare_exports(pd.read_csv(args.ledger),pd.read_csv(args.reference)),indent=2,allow_nan=False))
