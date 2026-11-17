-- 汇总必须与 ODS 来源独立计数一致，检测丢行和 JOIN 放大。
with actual as (
    select
        sum(simulated_vehicle_count) as vehicles,
        sum(simulated_service_order_count) as orders,
        sum(simulated_completed_order_count) as completed,
        sum(simulated_completed_service_cost) as completed_cost,
        sum(nhtsa_recall_campaign_count) as campaigns
    from {{ ref('vehicle_aftersales_dashboard') }}
), expected as (
    select
        (select count(*) from {{ source('ods', 'vehicles') }}) as vehicles,
        (select count(*) from {{ source('ods', 'service_orders') }}) as orders,
        (select count(*) from {{ source('ods', 'service_orders') }}
            where lower(trim(status)) = 'completed') as completed,
        coalesce((select sum(cost) from {{ source('ods', 'service_orders') }}
            where lower(trim(status)) = 'completed'), 0) as completed_cost,
        (select count(*) from (
            select distinct upper(trim(make)), upper(trim(model)), model_year,
                upper(trim(campaign_number))
            from {{ source('ods', 'nhtsa_recalls') }}
        ) AS distinct_campaigns) as campaigns
)
select actual.*
from actual cross join expected
where actual.vehicles is distinct from expected.vehicles
   or actual.orders is distinct from expected.orders
   or actual.completed is distinct from expected.completed
   or actual.completed_cost is distinct from expected.completed_cost
   or actual.campaigns is distinct from expected.campaigns
