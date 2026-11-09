"""Compare documented consequences, never a probability of a customs audit.

Rates are operator-checked scenarios. Unchecked/unknown policies stay unknown.
No tax advantage is allowed to promote or choose an HS candidate.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from .tax import amount, TaxError

POLICY_LABELS = {
    'unknown': 'Chưa đối chiếu chính sách',
    'none_identified': 'Chưa phát hiện yêu cầu trong phạm vi đã đối chiếu',
    'requirement_identified': 'Có yêu cầu giấy phép / kiểm tra / điều kiện',
    'prohibited': 'Có căn cứ về diện cấm; chuyển người phụ trách tuân thủ',
}


def compare_candidates(data, sku, case, catalogue, tax):
    """Pure deterministic comparison; preserve the analyst's candidate order."""
    codes = [r['code'] for r in data['candidates']]
    if len(codes) != len(set(codes)) or not 2 <= len(codes) <= 3:
        raise TaxError('Chọn 2–3 mã HS8 khác nhau để so sánh.')
    if any(c not in catalogue for c in codes):
        raise TaxError('Mỗi mã phải có trong danh mục Việt Nam đã nạp.')
    if not data.get('reviewer', '').strip():
        raise TaxError('Ghi người đối chiếu kịch bản.')
    day = case['classification_date']
    date.fromisoformat(day)
    value = data.get('customs_value_vnd')
    value = amount(value, 'Trị giá so sánh') if value is not None else None
    if value is not None and value <= 0:
        raise TaxError('Trị giá so sánh phải dương hoặc để trống.')
    rows, flags = [], []
    for item in data['candidates']:
        code = item['code']
        look = tax.lookup(code, day)
        scheme = item.get('scheme', 'MFN')
        trade = case['trade_type']
        if scheme not in look['rates'] or scheme in {'VAT', 'EXCISE', 'ENVIRONMENT'}:
            raise TaxError('Chế độ thuế không hợp lệ.')
        if (trade == 'export') != scheme.startswith('EXPORT'):
            raise TaxError('Chế độ thuế phải khớp luồng XNK của hồ sơ.')
        policy = item.get('policy_status', 'unknown')
        if policy not in POLICY_LABELS:
            raise TaxError('Trạng thái chính sách không hợp lệ.')
        if policy != 'unknown' and not all(item.get(k) for k in ['policy_source', 'policy_note', 'policy_checked']):
            raise TaxError('Nhận định chính sách cần căn cứ, phạm vi và xác nhận đã đối chiếu.')
        rate = item.get('duty_rate_percent')
        if rate is not None:
            rate = amount(rate, 'Thuế suất kịch bản')
            if rate > 2000 or not item.get('rate_checked') or not item.get('duty_rate_source', '').strip():
                raise TaxError('Mức thuế cần căn cứ và xác nhận tại ngày giao dịch; không tự lấy mức snapshot.')
        fta = scheme not in {'MFN', 'ordinary', 'EXPORT'}
        checks = item.get('eligibility', {})
        eligible = not fta or bool(
            data.get('origin_country', '').strip()
            and checks.get('co_status') == 'verified'
            and all(checks.get(k) is True for k in ['origin_rule_checked', 'transport_rule_checked', 'schedule_checked'])
        )
        if rate is not None and not eligible:
            raise TaxError('Chưa đủ điều kiện FTA để tính: xuất xứ, chứng từ, quy tắc và biểu áp dụng.')
        duty = value * rate / Decimal(100) if value is not None and rate is not None else None
        if policy == 'unknown': flags.append({'code': code, 'kind': 'policy_unknown'})
        if policy in {'requirement_identified', 'prohibited'}: flags.append({'code': code, 'kind': policy})
        if duty is None: flags.append({'code': code, 'kind': 'duty_scenario_incomplete'})
        if not eligible: flags.append({'code': code, 'kind': 'fta_conditions_unchecked'})
        rows.append({
            'code': code, 'path': catalogue[code]['path'], 'scheme': scheme,
            'snapshot_observation': look['rates'][scheme],
            'snapshot_date': look['snapshot_date'], 'source_sha256': look['source_sha256'],
            'policy_observation': look['goods_policy_observation'],
            'policy_status': policy, 'policy_label': POLICY_LABELS[policy],
            'policy_source': item.get('policy_source', ''), 'policy_note': item.get('policy_note', ''),
            'policy_checked': bool(item.get('policy_checked')), 'eligibility_checks': checks,
            'fta_eligibility': 'operator_checked' if fta and eligible else 'not_established' if fta else 'not_an_fta_scenario',
            'duty_rate_percent': str(rate) if rate is not None else None,
            'duty_rate_source': item.get('duty_rate_source', ''),
            'duty_vnd': str(duty.quantize(Decimal('.01'))) if duty is not None else None,
            'distinguishing_attributes': item.get('distinguishing_attributes', ''),
            'current_rates_legally_certified': False,
        })
    pairs = []
    for i, left in enumerate(rows):
        for right in rows[i+1:]:
            complete = left['duty_vnd'] is not None and right['duty_vnd'] is not None
            pairs.append({
                'code_a': left['code'], 'code_b': right['code'],
                'duty_difference_b_minus_a_vnd': str(Decimal(right['duty_vnd'])-Decimal(left['duty_vnd'])) if complete else None,
                'policy_differs': left['policy_status'] != right['policy_status'] if 'unknown' not in {left['policy_status'], right['policy_status']} else None,
                'unknown_policy_is_no_requirement': False,
            })
    reasons = []
    if sku['readiness']['missing_fields']: reasons.append('Thiếu thuộc tính bắt buộc đã được kiểm tra.')
    if any(f['status'] == 'conflict' for f in sku['facts']): reasons.append('Có thuộc tính mâu thuẫn cần giải quyết.')
    if any(r['policy_status'] == 'unknown' for r in rows): reasons.append('Chính sách của ít nhất một mã chưa được đối chiếu.')
    if any(p['policy_differs'] for p in pairs): reasons.append('Các mã dẫn tới chính sách khác nhau; cần kiểm tra tiêu chí phân loại trước khi chốt.')
    if any(r['policy_status'] == 'prohibited' for r in rows): reasons.append('Có kịch bản thuộc diện cấm theo căn cứ người dùng ghi; chuyển chuyên gia tuân thủ.')
    return {
        'version': 'comparison-1', 'sku_revision': sku['revision'],
        'analysis_id': sku.get('analysis_id'), 'classification_date': day, 'trade_type': case['trade_type'],
        'customs_value_vnd': str(value) if value is not None else None,
        'origin_country': data.get('origin_country', ''), 'reviewer': data['reviewer'],
        'rows': rows, 'pairs': pairs, 'flags': flags,
        'escalation': {'action': 'complete_information_or_consult_specialist' if reasons else 'human_classification_review',
                       'reasons': reasons, 'advance_ruling_option': 'Cân nhắc xin xác định trước khi đã có đủ hồ sơ kỹ thuật nhưng vẫn còn tranh chấp phân loại; đối chiếu thủ tục, lịch hàng và thời hạn đang áp dụng.',
                       'is_statutory_eligibility_determination': False},
        'audit_probability': None, 'recommended_hs_code': None, 'penalty_estimated': False,
        'tax_cost_used_to_rank_codes': False, 'scope': 'Chỉ so sánh thuế XNK theo tỷ lệ phần trăm do người dùng đối chiếu. Chưa gồm VAT, TTĐB, BVMT, phòng vệ thương mại, phạt hoặc chi phí chậm hàng; không phải tổng nghĩa vụ thuế.',
    }
