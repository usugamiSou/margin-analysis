from enum import Enum, unique, auto


@unique
class Exchange(Enum):
    CFE = auto()
    SH = auto()
    SZ = auto()
    SHFE = auto()
    DCE = auto()
    CZCE = auto()
    GFEX = auto()

    @classmethod
    def from_string(cls, string):
        match string:
            case 'CCFX' | 'CFE':
                return Exchange.CFE
            case 'XSHG' | 'SH':
                return Exchange.SH
            case 'XSHE' | 'SZ':
                return Exchange.SZ
            case 'XSGE' | 'SHFE':
                return Exchange.SHFE
            case 'XZCE' | 'CZCE':
                return Exchange.CZCE
            case 'XDCE' | 'DCE':
                return Exchange.DCE
            case 'GFEX':
                return Exchange.GFEX


@unique
class PositionType(Enum):
    Future = auto()
    Option = auto()
    Stock = auto()

@unique
class FutureVariety(Enum):
    # 中国金融期货交易所
    IF = 'IF'
    IC = 'IC'
    IM = 'IM'
    IH = 'IH'

    # 上海期货交易所
    # TODO

    # 大连商品交易所
    A = 'A'    # 黄大豆1号
    B = 'B'    # 黄大豆2号
    M = 'M'    # 豆粕
    Y = 'Y'    # 豆油
    P = 'P'    # 棕榈油
    C = 'C'     # 玉米
    CS = 'CS'    # 玉米淀粉
    RR = 'RR'    # 粳米
    JD = 'JD'    # 鸡蛋
    LH = 'LH'    # 生猪
    FB = 'FB'    # 纤维板
    BB = 'BB'    # 胶合板
    LG = 'LG'    # 玻璃
    JM = 'JM'    # 焦煤
    J = 'J'    # 焦炭
    I = 'I'    # 铁矿石
    L = 'L'    # 聚乙烯
    V = 'V'    # 聚氯乙烯
    PP = 'PP'    # 聚丙烯
    EG = 'EG'    # 乙二醇
    EB = 'EB'    # 苯乙烯
    PG = 'PG'    # 液化石油气
    BZ = 'BZ'    # 纯苯

    # 郑州商品交易所

    # TODO

    # 广州期货交易所
    # TODO

    # 上海证券交易所、深圳证券交易所
    ETF = 'ETF'    # 期权标的, 非期货
    
    @classmethod
    def is_commodity_pair(cls, variety1, variety2):
        return ((variety1, variety2) in cls._commodity_pairs or
                (variety2, variety1) in cls._commodity_pairs)


FutureVariety._commodity_pairs = (
        # 大连商品交易所
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

        # 郑州商品交易所
        # TODO
    )
