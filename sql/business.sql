-- 全部为教学模拟数据；不是福特内部数据。重复执行不会插入重复主键。
CREATE SCHEMA IF NOT EXISTS business;
CREATE TABLE IF NOT EXISTS business.dealers (
  dealer_id integer PRIMARY KEY,
  dealer_name text NOT NULL,
  region text NOT NULL,
  is_synthetic boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS business.vehicles (
  vehicle_id integer PRIMARY KEY,
  vehicle_code text NOT NULL UNIQUE,
  dealer_id integer NOT NULL REFERENCES business.dealers,
  make text NOT NULL,
  model text NOT NULL,
  model_year integer NOT NULL,
  sale_date date NOT NULL,
  sale_price numeric(12,2) NOT NULL CHECK (sale_price > 0),
  is_synthetic boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS business.service_orders (
  order_id integer PRIMARY KEY,
  vehicle_id integer NOT NULL REFERENCES business.vehicles,
  service_date date NOT NULL,
  service_type text NOT NULL,
  status text NOT NULL CHECK (status IN ('completed','open')),
  cost numeric(12,2) NOT NULL CHECK (cost >= 0),
  is_synthetic boolean NOT NULL DEFAULT true
);
INSERT INTO business.dealers
SELECT i, 'Demo Dealer ' || i, (ARRAY['West','East','Central'])[(i-1)%3+1], true
FROM generate_series(1,6) AS i ON CONFLICT DO NOTHING;
INSERT INTO business.vehicles
SELECT i, 'DEMO-' || lpad(i::text,6,'0'), (i-1)%6+1,
  'FORD', (ARRAY['ESCAPE','EXPLORER','F-150'])[(i-1)%3+1], 2020,
  date '2024-01-01' + (i%365), 25000 + (i%100)*250, true
FROM generate_series(1,300) AS i ON CONFLICT DO NOTHING;
INSERT INTO business.service_orders
SELECT i, (i-1)%300+1, date '2025-01-01' + (i%365),
  (ARRAY['maintenance','inspection','repair'])[(i-1)%3+1],
  CASE WHEN i%5=0 THEN 'open' ELSE 'completed' END,
  80 + (i%40)*15, true
FROM generate_series(1,600) AS i ON CONFLICT DO NOTHING;
