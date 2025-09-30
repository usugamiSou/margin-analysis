class Exchange:
    CFFEX = 'CFFEX'
    SSE = 'SSE'
    SZSE = 'SZSE'
    SHFE = 'SHFE'
    CZCE = 'CZCE'
    DCE = 'DCE'
    GFEX = 'GFEX'

    EquityExchanges = {CFFEX, SSE, SZSE}
    CommodityExchanges = {SHFE, DCE, CZCE, GFEX}

    @staticmethod
    def from_code(exchange_code: str) -> str:
        exchange_code = exchange_code.upper()
        match exchange_code:
            case 'CFE' | 'CCFX' | 'CFFEX':
                return Exchange.CFFEX
            case 'SH' | 'XSHG':
                return Exchange.SSE
            case 'SZ' | 'XSHE':
                return Exchange.SZSE
            case 'SHFE' | 'XSGE':
                return Exchange.SHFE
            case 'DZCE' | 'XZCE':
                return Exchange.CZCE
            case 'DCE' |'XDCE':
                return Exchange.DCE
            case 'GFEX':
                return Exchange.GFEX
            case _:
                raise ValueError(f'Invalid exchange code: {exchange_code}.')


class PositionType:
    Future = 'Future'
    Option = 'Option'
    Stock = 'Stock'


class Variety:
    EquityVarieties = {
        'CFFEX': {
            'IF', 'IC', 'IM', 'IH',
            'IO', 'MO', 'HO',
        },
        'SSE': {
            '510050', '510300', '510500', '588000', '588080',
        },
        'SZSE': {
            '159901', '159915', '159919', '159922',
        },
    }

    CommodityVarieties = {
        'SHFE': {
            'CU', 'BC', 'AL', 'ZN', 'PB', 'NI', 'SN', 'AO', 'AD',
            'AU', 'AG', 'RB', 'WR', 'HC', 'SS', 'SC', 'LU', 'FU',
            'BU', 'BR', 'RU', 'NR', 'SP', 'OP', 'EC',
        },
        'DCE': {
            'A', 'B', 'M', 'Y', 'P', 'C', 'CS', 'RR', 'JD', 'LH',
            'FB', 'BB', 'LG', 'JM', 'J', 'I', 'L', 'V', 'PP',
            'EG', 'EB', 'PG', 'BZ',
        },
        'CZCE': set(),
        'GFEX': {
            'PS', 'LC', 'SI',
        },
    }

    @staticmethod
    def is_commodity_pair(variety1: str, variety2: str, exchange: str) -> bool:
        if (
            exchange not in Variety.CommodityPairs or
            variety1 not in Variety.CommodityVarieties[exchange] or
            variety2 not in Variety.CommodityVarieties[exchange]
        ):
            return False
        return frozenset((variety1, variety2)) in Variety.CommodityPairs[exchange]

    CommodityPairs = {
        'CZCE': set(),
        'DCE': {
            frozenset(('A', 'B')), frozenset(('A', 'M')), frozenset(('B', 'M')),
            frozenset(('Y', 'P')), frozenset(('C', 'CS')), frozenset(('JM', 'J')),
            frozenset(('JM', 'I')), frozenset(('J', 'I')), frozenset(('L', 'V')),
            frozenset(('L', 'PP')), frozenset(('L', 'EG')), frozenset(('L', 'EB')),
            frozenset(('L', 'PG')), frozenset(('V', 'PP')), frozenset(('V', 'EG')),
            frozenset(('V', 'EB')), frozenset(('V', 'PG')), frozenset(('PP', 'EG')),
            frozenset(('PP', 'EB')), frozenset(('PP', 'PG')), frozenset(('EG', 'EB')),
            frozenset(('EG', 'PG')), frozenset(('EB', 'PG')),
        },
    }
