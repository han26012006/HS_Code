"""Scalar validation: header labels are not values even when quoted correctly."""
import re
from .document_layout import norm
from .document_schema import label_field

HEADERS={'page','bill of lading','commercial invoice','packing list','declared value','place of delivery by on-carrier',
         'l/c issuing bank','mã','tên','name','address','địa chỉ','currency','measurement'}


def usable_metadata(field,value):
    value=value.strip();clean=re.sub(r'^[0-9①-⑳]+[.)\s]+','',norm(value)).strip(' :.')
    if clean in HEADERS or label_field(clean,True) or label_field(clean):return False
    if field=='currency':return bool(re.fullmatch(r'USD|EUR|JPY|VND|CNY|RMB|GBP|SGD',value))
    if field in {'importer','exporter','shipper','consignee'}:
        if re.match(r'^(?:mã|tax code|telephone|tel|fax|page)\b',clean):return False
        if re.fullmatch(r'[\d\W]+',value):return False
    return True
