select
    v.vehicle_id,
    v.dealer_id,
    d.region,
    upper(trim(v.make)) as make,
    upper(trim(v.model)) as model,
    cast(v.model_year as integer) as model_year,
    v.sale_date,
    v.sale_price,
    v.is_synthetic
from {{ source('ods', 'vehicles') }} v
left join {{ source('ods', 'dealers') }} d using (dealer_id)
