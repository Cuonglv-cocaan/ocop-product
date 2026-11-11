"""Explicit operator seed: one OPEN simulated request, no matching or selection."""
import json
from datetime import timedelta

import duckdb
import psycopg
from . import postgres, purchase, suppliers


def seed_request():
    items = suppliers.catalog_items()
    reference = items[0] if items else {}
    fields = dict(title='Nhu cầu mô phỏng: mua sản phẩm OCOP', category='Demo môn học',
                  description='DỮ LIỆU MÔ PHỎNG, không phải nhu cầu mua thực tế.', quantity='10', unit='hộp',
                  budget='1000000', budget_type='total', delivery_location='Địa điểm giao mô phỏng',
                  delivery_deadline=purchase.today() + timedelta(days=14), additional_requirements='Dùng cho kịch bản demo.',
                  source=reference.get('source', ''), product_id=reference.get('product_id', ''),
                  contact_name='Buyer mô phỏng', contact_email='buyer01@example.invalid', contact_phone='')
    values = purchase._request_values(fields)
    with postgres.transaction() as connection:
        buyer = connection.execute("SELECT id FROM business.users WHERE username='buyer01' AND role='buyer' AND active FOR SHARE").fetchone()
        if not buyer:
            raise ValueError('Cần buyer01 active với role buyer; không tự tạo hoặc đổi role tài khoản.')
        placeholders = ','.join(['%s'] * len(values))
        columns = ','.join(purchase.REQUEST_FIELDS)
        row = connection.execute(f'''INSERT INTO business.purchase_requests(buyer_id,demo_key,{columns})
            VALUES (%s,'ocop-demo-purchase-open',{placeholders}) ON CONFLICT(demo_key) DO NOTHING RETURNING id''',
            (buyer[0], *values)).fetchone()
        if row:
            purchase._event(connection, row[0], {'id': buyer[0]}, 'demo_seed', 'Operator tạo phiếu MÔ PHỎNG ở trạng thái mới; chưa phân công hoặc lựa chọn.')
    return {'created': int(row is not None), 'skipped': int(row is None)}


def main():
    try:
        print(json.dumps(seed_request(), ensure_ascii=False))
    except ValueError as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1
    except (psycopg.Error, duckdb.Error, OSError):
        print(json.dumps({'error': 'Không thể seed; kiểm tra migration 005 và cấu hình.'}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
