select make, model, model_year, count(*) as rows_per_model
from {{ ref('vehicle_aftersales_dashboard') }}
group by make, model, model_year
having count(*) > 1 or make is null or model is null or model_year is null
