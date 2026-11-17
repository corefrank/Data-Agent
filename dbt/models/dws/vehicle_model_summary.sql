-- 三个来源先聚合到同一粒度，再关联，避免召回与工单之间的多对多放大。
with vehicles as (
    select make, model, model_year, count(*) as vehicle_count
    from {{ ref('vehicle_detail') }}
    group by make, model, model_year
), orders as (
    select make, model, model_year,
        count(*) as service_order_count,
        count(*) filter (where status = 'completed') as completed_order_count,
        sum(cost) filter (where status = 'completed') as completed_service_cost
    from {{ ref('service_order_detail') }}
    group by make, model, model_year
), recalls as (
    select make, model, model_year,
        count(distinct campaign_number) as recall_campaign_count
    from {{ ref('recall_detail') }}
    group by make, model, model_year
), model_keys as (
    select make, model, model_year from vehicles
    union
    select make, model, model_year from orders
    union
    select make, model, model_year from recalls
)
select k.make, k.model, k.model_year,
    coalesce(v.vehicle_count, 0) as vehicle_count,
    coalesce(o.service_order_count, 0) as service_order_count,
    coalesce(o.completed_order_count, 0) as completed_order_count,
    coalesce(o.completed_service_cost, 0) as completed_service_cost,
    coalesce(r.recall_campaign_count, 0) as recall_campaign_count
from model_keys k
left join vehicles v using (make, model, model_year)
left join orders o using (make, model, model_year)
left join recalls r using (make, model, model_year)
