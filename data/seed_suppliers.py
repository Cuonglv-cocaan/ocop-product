"""Explicit simulated supplier fixtures; never run at app startup."""
import json

import duckdb
import psycopg
from . import postgres, suppliers

DEMO_UNITS = (('ocop-demo-unit-a', 'Đơn vị A (Mô phỏng)', 'seller01'),
              ('ocop-demo-unit-b', 'Đơn vị B (Mô phỏng)', 'seller02'))


def seed_suppliers():
    products = suppliers.catalog_items()
    if len(products) < 2:
        raise ValueError('Catalog cần ít nhất 2 sản phẩm có khóa source + product_id hợp lệ.')
    created = skipped = 0
    with postgres.transaction() as connection:
        connection.execute('SELECT pg_advisory_xact_lock(674091825)')
        users = {}
        for username, role in (('seller01', 'seller'), ('seller02', 'seller'), ('admin01', 'admin')):
            row = connection.execute('SELECT id,role,active FROM business.users WHERE username=%s FOR SHARE',
                                     (username,)).fetchone()
            if not row or row[1] != role or not row[2]:
                raise ValueError(f'Cần tài khoản {username} đang active với role {role}. Chạy seed tài khoản riêng trước.')
            users[username] = row[0]
        for (demo_key, name, username), product in zip(DEMO_UNITS, products):
            row = connection.execute('''INSERT INTO business.suppliers
                (name,description,status,created_by,reviewed_by,reviewed_at,demo_key,is_demo)
                VALUES (%s,%s,'approved',%s,%s,CURRENT_TIMESTAMP,%s,TRUE)
                ON CONFLICT (demo_key) DO NOTHING RETURNING id''',
                (name, 'DỮ LIỆU MÔ PHỎNG cho demo môn học; không phải nhà cung cấp đã xác minh.',
                 users[username], users['admin01'], demo_key)).fetchone()
            if row is None:
                skipped += 1
                continue
            supplier_id = row[0]
            connection.execute('INSERT INTO business.supplier_members(supplier_id,user_id) VALUES (%s,%s)',
                               (supplier_id, users[username]))
            connection.execute('''INSERT INTO business.supplier_products(supplier_id,source,product_id,capacity_description)
                VALUES (%s,%s,%s,%s)''', (supplier_id, product['source'], product['product_id'],
                                         'Liên kết cung ứng mô phỏng; chưa xác minh năng lực thực tế.'))
            created += 1
    return {'created': created, 'skipped': skipped}


def main():
    try:
        print(json.dumps(seed_suppliers(), ensure_ascii=False))
    except ValueError as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1
    except (psycopg.Error, duckdb.Error, OSError):
        print(json.dumps({'error': 'Không thể seed. Kiểm tra migration 004, kết nối và catalog.'}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
