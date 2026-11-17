# 实测记录

验证日期：2026-11-17（北京时间）。

## 已实际运行

- Python 3.12；dlt 1.32.0；DuckDB 1.5.6；psycopg 3.3.9。
- PostgreSQL 17.11 本地真实服务（不是 SQLite 或内存假实现）。
- `src.seed` 执行 DDL、主外键约束与模拟数据生成。
- NHTSA 三组真实 GET 请求：FORD ESCAPE 2020 = 23；EXPLORER 2020 = 33；F-150 2020 = 11。
- PostgreSQL page_size=100：经销商 1 页 / 6 行，车辆 3 页 / 300 行，售后工单 6 页 / 600 行。
- dlt 完整 extract/normalize/load 成功；ODS 4 张业务表共 973 行（含 67 行召回车型记录；不等于 67 个跨车型去重后的全局召回活动）。
- 验收：目标与来源快照行数一致、业务主键唯一/非空、业务外键有效、run_id 一致、模拟来源标签正确。
- 完整快照重放一次，行数不增加，验收再次通过。
- `sql/inspect_ods.sql` 的四条示例查询执行成功。
- pytest：4 passed（异常 API 响应、召回键跨车型保留、HTTP 重试策略、非法分页大小）。

## 验证范围限制

- 当前环境没有 Docker；PostgreSQL 采用本地二进制服务验证。提供的 compose.yaml 未在 Docker Desktop / Windows 上实际启动。
- 未对真实 NHTSA 服务注入限流故障；重试策略进行了单元检查，不声称完成公网故障演练。
- 仅验证小规模教学数据；无性能压测、CDC、生产调度或多写入者并发支持。


## 数仓分层验证

- 用随包快照重放 dlt 加载，ODS 验收通过。
- dbt Core 1.11.17，dbt-duckdb 1.11.1。5 张下游表创建成功，13 项 dbt 数据测试通过。
- ADS 三个车型均为 100 辆模拟车辆、200 条模拟工单和 160 条完成工单，完成率 80%。召回活动数依次为 Escape 23、Explorer 33、F-150 11。
- dbt 从 ODS 独立核对 ADS 的五项汇总指标，包括已完成工单费用。

