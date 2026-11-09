"""A dated registry status is not a guarantee that all law changes are known."""
from datetime import date

AHTN2022_START = '2022-12-30'


def dated_registry(registry, as_of):
    date.fromisoformat(as_of)
    rows = []
    for source in registry['rules']:
        start, end = source.get('effective_from'), source.get('effective_to_exclusive')
        status = 'not_yet_effective' if start and as_of < start else 'no_longer_effective' if end and as_of >= end else 'in_recorded_effective_period' if start else 'effective_period_not_recorded'
        rows.append(dict(source, status_on_date=status))
    return {'as_of': as_of, 'registry_checked_on': registry['as_of'], 'sources': rows,
            'covers_all_amendments': False,
            'warning': 'Phân biệt ngày ban hành và ngày hiệu lực; trạng thái chỉ theo các mốc đã ghi trong registry, cần đối chiếu thay đổi và quy định chuyển tiếp.'}
