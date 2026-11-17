select
    o.order_id,
    o.vehicle_id,
    v.make,
    v.model,
    v.model_year,
    o.service_date,
    lower(trim(o.service_type)) as service_type,
    lower(trim(o.status)) as status,
    o.cost,
    o.is_synthetic
from {{ source('ods', 'service_orders') }} o
left join {{ ref('vehicle_detail') }} v using (vehicle_id)
