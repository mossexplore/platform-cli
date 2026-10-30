"""Compact numeric quality data for Agent statistics, before output budgeting."""

from decimal import Decimal

from wiserec_cli.errors import ApiError


def null_rates_page(page):
    rates = []
    for index, item in enumerate(page['items'], start=1):
        value = item.get('nullValueRate')
        if value is not None:
            if (isinstance(value, bool) or not isinstance(value, (int, float, Decimal))
                    or (isinstance(value, Decimal) and not value.is_finite())
                    or not 0 <= value <= 1):
                raise ApiError(f'第 {index} 条特征的 nullValueRate 不是有效的 0～1 数值')
            # Decimal must also be numeric in the actual serialized tool result.
            if isinstance(value, Decimal):
                value = int(value) if value == value.to_integral_value() else float(value)
        rates.append(value)
    return {'nullValueRates': rates, 'count': page['count'],
            'pageIndex': page['pageIndex'], 'pageSize': page['pageSize']}
