ANSI_TABLE = [
    {"range": (2, 8),       "Reduced": (4, 5.46), "Normal": (4, 1.49), "Tightened": (5, 1.34)},
    {"range": (9, 15),      "Reduced": (4, 5.46), "Normal": (4, 1.49), "Tightened": (5, 1.34)},
    {"range": (16, 25),     "Reduced": (4, 5.46), "Normal": (4, 1.49), "Tightened": (7, 2.13)},

    {"range": (26, 50),     "Reduced": (4, 5.46), "Normal": (5, 3.33), "Tightened": (10, 2.14)},
    {"range": (51, 90),     "Reduced": (4, 5.46), "Normal": (7, 3.54), "Tightened": (15, 2.09)},
    {"range": (91, 150),    "Reduced": (4, 5.46), "Normal": (10, 3.27), "Tightened": (20, 2.03)},

    {"range": (151, 280),   "Reduced": (4, 5.46), "Normal": (15, 3.06), "Tightened": (25, 2.00)},
    {"range": (281, 400),   "Reduced": (5, 5.82), "Normal": (20, 2.93), "Tightened": (35, 1.87)},
    {"range": (401, 500),   "Reduced": (5, 5.82), "Normal": (25, 2.86), "Tightened": (35, 1.87)},

    {"range": (501, 1200),  "Reduced": (7, 5.34), "Normal": (35, 2.66), "Tightened": (50, 1.73)},
    {"range": (1201, 3200), "Reduced": (10, 4.72), "Normal": (50, 2.47), "Tightened": (75, 1.59)},
    {"range": (3201, 100000),"Reduced": (15, 4.32), "Normal": (75, 2.27), "Tightened": (100, 1.52)},
]


def get_sampling_values(lot_size: int, sampling_type: str):
    for row in ANSI_TABLE:
        low, high = row["range"]

        if low <= lot_size <= high:
            n, M = row[sampling_type]   
            return {
                "sample_size": n,
                "acceptance_limit": M,
                "type": sampling_type,
                "lot_size": lot_size
            }

    raise ValueError(f"No sampling range found for lot size {lot_size}")
