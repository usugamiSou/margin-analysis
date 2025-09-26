from enum import Enum, unique, auto


@unique
class Exchange(Enum):
    CFE = auto()
    SSE = auto()
    SZSE = auto()
    SHFE = auto()
    DCE = auto()
    CZCE = auto()
    GFEX = auto()

@unique
class PositionType(Enum):
    Future = auto()
    Option = auto()
    Stock = auto()

@unique
class OptionVariety(Enum):
    ETF = auto()
    Index = auto()
    Commodity = auto()

@unique
class FutureVariety(Enum):
    # CFE
    IF = auto()
    IC = auto()
    IM = auto()
    IH = auto()
    IO = auto()
    MO = auto()
    HO = auto()

    # SHFE
    CU = auto()    # 铜
    BC = auto()    # 铜(BC)
    AL = auto()    # 铝
    ZN = auto()    # 锌
    PB = auto()    # 铅
    NI = auto()    # 镍
    SN = auto()    # 锡
    AO = auto()    # 氧化铝
    AD = auto()    # 铸造铝合金
    AU = auto()    # 黄金
    AG = auto()    # 白银
    RB = auto()    # 螺纹钢
    WR = auto()    # 线材
    HC = auto()    # 热轧卷板
    SS = auto()    # 不锈钢
    SC = auto()    # 原油
    LU = auto()    # 低硫燃料油
    FU = auto()    # 燃料油
    BU = auto()    # 石油沥青
    BR = auto()    # 合成橡胶
    RU = auto()    # 天然橡胶
    NR = auto()    # 20号胶
    SP = auto()    # 纸浆
    OP = auto()    # 胶版印刷纸
    EC = auto()    # SCFIS欧线

    # DCE
    A = auto()    # 黄大豆1号
    B = auto()    # 黄大豆2号
    M = auto()    # 豆粕
    Y = auto()    # 豆油
    P = auto()    # 棕榈油
    C = auto()     # 玉米
    CS = auto()    # 玉米淀粉
    RR = auto()    # 粳米
    JD = auto()    # 鸡蛋
    LH = auto()    # 生猪
    FB = auto()    # 纤维板
    BB = auto()    # 胶合板
    LG = auto()    # 玻璃
    JM = auto()    # 焦煤
    J = auto()    # 焦炭
    I = auto()    # 铁矿石
    L = auto()    # 聚乙烯
    V = auto()    # 聚氯乙烯
    PP = auto()    # 聚丙烯
    EG = auto()    # 乙二醇
    EB = auto()    # 苯乙烯
    PG = auto()    # 液化石油气
    BZ = auto()    # 纯苯

    # CZCE

    # TODO

    # GFEX
    # TODO

    # SSE, SZSE
    ETF = auto()    # 期权标的, 非期货
    
    @classmethod
    def is_commodity_pair(cls, variety1, variety2):
        return ((variety1, variety2) in cls._commodity_pairs or
                (variety2, variety1) in cls._commodity_pairs)


FutureVariety._commodity_pairs = (
        # DCE
        (FutureVariety.A, FutureVariety.B),
        (FutureVariety.A, FutureVariety.M),
        (FutureVariety.B, FutureVariety.M),
        (FutureVariety.Y, FutureVariety.P),
        (FutureVariety.C, FutureVariety.CS),
        (FutureVariety.JM, FutureVariety.J),
        (FutureVariety.JM, FutureVariety.I),
        (FutureVariety.J, FutureVariety.I),
        (FutureVariety.L, FutureVariety.V),
        (FutureVariety.L, FutureVariety.PP),
        (FutureVariety.L, FutureVariety.EG),
        (FutureVariety.L, FutureVariety.EB),
        (FutureVariety.L, FutureVariety.PG),
        (FutureVariety.V, FutureVariety.PP),
        (FutureVariety.V, FutureVariety.EG),
        (FutureVariety.V, FutureVariety.EB),
        (FutureVariety.V, FutureVariety.PG),
        (FutureVariety.PP, FutureVariety.EG),
        (FutureVariety.PP, FutureVariety.EB),
        (FutureVariety.PP, FutureVariety.PG),
        (FutureVariety.EG, FutureVariety.EB),
        (FutureVariety.EG, FutureVariety.PG),
        (FutureVariety.EB, FutureVariety.PG),

        # CZCE
        # TODO
    )
