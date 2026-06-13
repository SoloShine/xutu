# src/bedrock/config/volume_type_matrix.py
"""卷类型矩阵静态常量表。SP2 建基础设施，配额查询逻辑在 SP5。"""

VOLUME_TYPE_MATRIX = {
    "opening": {
        "may_plant_per_chapter": (3, 4),
        "mature_decline_floor": 0,
        "pruning_quota": 0,
        "net_balance_range": (5, 10),
    },
    "advancing": {
        "may_plant_per_chapter": (1, 2),
        "mature_decline_floor": "floor(N/3)",
        "pruning_quota": 10,
        "net_balance_range": (-2, 2),
    },
    "climax": {
        "may_plant_per_chapter": (0, 1),
        "mature_decline_floor": "floor(N/2)",
        "pruning_quota": 15,
        "net_balance_range": (-99, -5),
    },
    "epilogue": {
        "may_plant_per_chapter": (0, 0),
        "mature_decline_floor": "N",
        "pruning_quota": 9999,
        "net_balance_range": (-9999, -1),
    },
    "multi-pov": {
        "may_plant_per_chapter": (2, 3),
        "mature_decline_floor": "floor(N/4)",
        "pruning_quota": 8,
        "net_balance_range": (0, 0),
    },
}


def get_matrix(volume_type):
    """返回该卷类型的阈值矩阵。未知类型 raise KeyError。"""
    return VOLUME_TYPE_MATRIX[volume_type]
