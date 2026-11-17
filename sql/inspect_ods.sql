-- 先用 Python check 验收，再执行以下查询查看数据。
SELECT * FROM ods.dealers;
SELECT make, model, model_year, count(*) AS inventory_count
FROM ods.vehicles GROUP BY ALL ORDER BY model;
SELECT model, count(DISTINCT campaign_number) AS recall_campaigns
FROM ods.nhtsa_recalls GROUP BY model ORDER BY recall_campaigns DESC;

-- 先将召回聚合到车型年款粒度，防止 JOIN 放大车辆数/销售额。
-- 这里只表示车型年款存在召回记录，不代表这辆模拟车辆的 VIN 确定受影响。
WITH recalls AS (
  SELECT make, model, model_year, count(DISTINCT campaign_number) AS campaigns
  FROM ods.nhtsa_recalls GROUP BY ALL
)
SELECT v.model, count(*) AS simulated_vehicles, max(coalesce(r.campaigns,0)) AS model_year_campaigns
FROM ods.vehicles v LEFT JOIN recalls r USING(make,model,model_year)
GROUP BY v.model ORDER BY v.model;
