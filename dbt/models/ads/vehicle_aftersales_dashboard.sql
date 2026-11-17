-- 发布给看板和 Data Agent 的指标表，完成率为 0 到 100 的数值。
select
    make,
    model,
    model_year,
    vehicle_count as simulated_vehicle_count,
    service_order_count as simulated_service_order_count,
    completed_order_count as simulated_completed_order_count,
    round(100.0 * completed_order_count / nullif(service_order_count, 0), 2)
        as simulated_completion_pct,
    completed_service_cost as simulated_completed_service_cost,
    recall_campaign_count as nhtsa_recall_campaign_count
from {{ ref('vehicle_model_summary') }}
