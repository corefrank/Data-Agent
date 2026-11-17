select distinct
    upper(trim(campaign_number)) as campaign_number,
    upper(trim(make)) as make,
    upper(trim(model)) as model,
    cast(model_year as integer) as model_year,
    cast(try_strptime(trim(report_received_date_raw), '%d/%m/%Y') as date) as report_received_date,
    nullif(trim(component), '') as component,
    is_synthetic
from {{ source('ods', 'nhtsa_recalls') }}
