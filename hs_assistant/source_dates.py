"""Read source dates without turning ambiguous locale dates into invented facts."""
import calendar
import re
from datetime import date


def source_date(value):
    clean=re.sub(r'\s*([/.,-])\s*',r'\1',value.strip())
    iso=re.fullmatch(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',clean)
    if iso:
        try:return {'iso':date(*map(int,iso.groups())).isoformat(),'status':'extracted'}
        except ValueError:return None
    month_names={name.casefold():i for i in range(1,13) for name in (calendar.month_name[i],calendar.month_abbr[i])}
    named=re.fullmatch(r'(\d{1,2})[ /.,-]+([A-Za-z]+)[ /.,-]+(\d{4})',clean)
    if named and named.group(2).casefold() in month_names:
        try:return {'iso':date(int(named.group(3)),month_names[named.group(2).casefold()],int(named.group(1))).isoformat(),'status':'extracted'}
        except ValueError:return None
    numeric=re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',clean)
    if numeric:
        first,second,year=map(int,numeric.groups())
        if first<=12 and second<=12:return {'iso':None,'status':'needs_review'}
        day,month=(first,second)if first>12 else(second,first)
        try:return {'iso':date(year,month,day).isoformat(),'status':'extracted'}
        except ValueError:return None
    return None
