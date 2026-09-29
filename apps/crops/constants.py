_CWT = "$/cwt"

COMMODITY_TICKERS = [
    # Grains
    {"ticker": "ZC=F", "name": "Corn",           "unit": "$/bu",  "divisor": 100},
    {"ticker": "ZS=F", "name": "Soybeans",        "unit": "$/bu",  "divisor": 100},
    {"ticker": "ZW=F", "name": "Wheat (CBOT)",    "unit": "$/bu",  "divisor": 100},
    {"ticker": "KE=F", "name": "Wheat (KC HRW)",  "unit": "$/bu",  "divisor": 100},
    {"ticker": "ZO=F", "name": "Oats",            "unit": "$/bu",  "divisor": 100},
    {"ticker": "ZM=F", "name": "Soybean Meal",    "unit": "$/ton", "divisor": 1},
    {"ticker": "ZL=F", "name": "Soybean Oil",     "unit": "$/lb",  "divisor": 100},
    # Livestock
    {"ticker": "LE=F", "name": "Live Cattle",     "unit": _CWT, "divisor": 1},
    {"ticker": "GF=F", "name": "Feeder Cattle",   "unit": _CWT, "divisor": 1},
    {"ticker": "HE=F", "name": "Lean Hogs",       "unit": _CWT, "divisor": 1},
    # Dairy
    {"ticker": "DC=F", "name": "Class III Milk",  "unit": _CWT, "divisor": 1},
    # Fiber
    {"ticker": "CT=F", "name": "Cotton",          "unit": "$/lb",  "divisor": 100},
]
