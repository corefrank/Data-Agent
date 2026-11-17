# 车辆与售后数据工程 

数据路径为 NHTSA API 和 PostgreSQL 模拟业务库 → Python + dlt → DuckDB ODS → dbt DWD/DWS/ADS。
已有 DuckDB ODS 或想直接查看分层结果时，从第 6 节开始。

## 业务问题与边界

用模拟经销商的车辆、售后工单，结合公开召回记录，为后续分析“哪些车型年款存在较多召回活动、售后工单与成本如何分布”准备数据。

- NHTSA：真实公开数据，FORD / ESCAPE、EXPLORER、F-150 / 2020 年款。
- PostgreSQL：6 家模拟经销商、300 辆模拟车辆、600 条模拟售后工单；确定性 SQL 生成，明确 `is_synthetic=true`。
- 两个来源按 `make + model + model_year` 关联。该关联仅说明车型年款存在召回活动，**不能证明单辆车的 VIN 受影响**。
- 不提供 VIN，不编造召回维修完成情况；模拟售后工单不是召回维修记录。
- 数据中没有销量分母或保有量分母，召回活动数不能称为“故障率”。

## 1. 最短运行路径（Windows PowerShell / Linux 都可用）

前提：Python 3.11+、uv、Docker（Windows 启动 Docker Desktop）。在解压后的 `ford_data_mvp` 目录打开终端。

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
```

复制配置，二选一：

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Linux / WSL
cp .env.example .env
```

本地默认数据库用户名 `demo`、密码 `local_demo_only`、数据库 `ford_demo`、端口 `5433`。如修改密码，同时修改 `.env` 中的 `POSTGRES_PASSWORD` 和 `PG_DSN`。端口冲突时同时修改 compose 的主机端口与 DSN。

```bash
docker compose up -d --wait
uv run python -m src.seed
uv run python -m src.pipeline
uv run python -m src.check
```

`seed` 输出应为 6 / 300 / 600；召回数据条数以 API 实际响应为准。查看进程：`docker compose ps`。停止：`docker compose stop`（保留数据）。

`uv run` 自动使用当前项目 `.venv`，不需要手动激活。若 `--wait` 不被旧版 Compose 支持，使用 `docker compose up -d` 并通过 `docker compose ps` 等待 healthy。

## 2. 没有 Docker，也可先演示 dlt 加载

压缩包里的 `data/example_snapshot/` 是本次真实运行保存的完整快照：NHTSA 为真实 API 响应，业务数据来自真实 PostgreSQL 中的模拟表。

```bash
uv run python -m src.pipeline --replay data/example_snapshot
uv run python -m src.check --run data/example_snapshot
```

这条路径可离线加载快照，**不代表你已经在自己电脑上部署或运行了 PostgreSQL 抽取**。依赖首次安装仍需要网络。实时完整流程使用上一节。

## 3. 查看数据

```bash
uv run python -c "import duckdb; c=duckdb.connect('data/warehouse.duckdb',read_only=True); print(c.sql('SELECT model, count(DISTINCT campaign_number) AS campaigns FROM ods.nhtsa_recalls GROUP BY model'))"
```

更多查询：`sql/inspect_ods.sql`。dbt 使用同一个 `data/warehouse.duckdb` 文件。

| ODS 表 | 粒度 / 关键字段 |
|---|---|
| ods.dealers | 每个 dealer_id 一行 |
| ods.vehicles | 每个 vehicle_id 一行；dealer_id 关联经销商 |
| ods.service_orders | 每个 order_id 一行；vehicle_id 关联车辆 |
| ods.nhtsa_recalls | campaign_number × make × model × model_year × component |

dlt 还会创建 `_dlt_*` 技术表及字段，用于加载追踪，它们不是业务表。

## 4. 代码阅读顺序（约 45–60 分钟）

1. `sql/business.sql`：看三张业务表和外键，再看如何生成模拟记录。
2. `src/seed.py`：通过 psycopg 执行 SQL，初始化 PostgreSQL。
3. `src/extract.py`：API 提取、响应校验、数据库主键分页、失败重试、原始快照。
4. `src/load.py`：Python 类型转换、dlt resource、`pipeline.run` 加载 ODS。
5. `src/pipeline.py`：把提取和加载串起来；`src/check.py` 做加载验收。

### Python 与 dlt 各做什么？

- Python requests：访问 API，超时和 HTTP 重试。
- psycopg：读 PostgreSQL，主键分页。
- Python：来源标记、原始 JSON 留存，金额恢复 Decimal、日期恢复 date。
- dlt：将资源流规范化为关系表、推断/声明字段类型、创建目标表并加载 DuckDB。
- 本版保留召回原始日期字符串；统一日期解析、业务清洗放到后续 DWD。

### 分页与重试

- NHTSA 官方 `recallsByVehicle` 接口没有文档化的 page 参数，一组车型年款请求获取其结果，不伪造分页。
- PostgreSQL 用 `WHERE id > last_id ORDER BY id LIMIT page_size`，默认 100 行/页。修改：`uv run python -m src.pipeline --page-size 50`。
- 三张表在同一只读 REPEATABLE READ 事务抽取，避免分页期间读到不一致快照。
- HTTP 对连接错误及 429/500/502/503/504 有界重试（最多 4 次重试），指数退避并遵循 Retry-After；404 等错误直接失败。
- PostgreSQL 连接/操作错误最多重试整个抽取 3 次；权限、SQL 错误不会盲目重试。
- 任一来源抓取失败不会启动 dlt 加载；失败目录保留 `manifest.json`。
- dlt 加载失败标记 `load_failed`，应先检查异常，再重放对应完整快照；不承诺跨全部来源/全部目标表的发布事务。

### 为什么是全量快照 replace？

这是小数据量教学版。每次成功运行替换四张 ODS 表，既不会重复堆积，也能同步源端删除。不是 CDC，也没有实现跨运行增量水位。主键分页只是在一次全量抽取中分批读取，不能称为“增量同步”。

ODS 是当前快照；`data/runs/<run_id>/` 保存历史原始响应、业务快照和 manifest。可以用 `--replay data/runs/<run_id>` 重跑。不要同时运行多个写入进程。

全量原始数据在小规模演示中读入内存。若扩展百万行，需要流式落地/加载、增量水位、调度与发布机制；本版不声称具备这些能力。

### 留存与排错

- `data/warehouse.duckdb`：最终数据库。
- `data/runs/<run_id>/manifest.json`：来源 URL、抓取时间、原始条数、PG 页数、状态、dlt load IDs。
- `data/runs/<run_id>/nhtsa_*.json`：API 原始响应。
- `data/runs/<run_id>/pg_*.json`：数据库快照。
- `data/pipelines/`：dlt 本地状态。

NHTSA 网络失败时先确认 URL 的 GET 请求可访问。HEAD 请求可能返回 403，不能据此判断 GET 不可用。不要把失败替换成空列表继续覆盖旧数据。本项目不会静默切换假数据。

## 5. 验证

```bash
uv run python -m pytest -q
uv run python -m src.check
```

`check` 核对最新快照的来源条数、主键唯一性、外键、run_id、真实/模拟标签。重放一次再验收，可验证重复运行不会增加行数。附 `VALIDATION.md` 记录作者实际验证范围。

## 6. 用 dbt 构建 DWD、DWS、ADS

在项目根目录运行。压缩包附带已经生成的 DuckDB，可以直接构建。如果想从 ODS 开始复现，可先执行第 1 节的实时流程或第 2 节的快照重放。

```powershell
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run python -c "import duckdb; c=duckdb.connect('data/warehouse.duckdb',read_only=True); print(c.sql('SELECT * FROM ads.vehicle_aftersales_dashboard ORDER BY model'))"
```

| 层 | 数据表 | 作用 |
|---|---|---|
| ODS | `ods.dealers`、`ods.vehicles`、`ods.service_orders`、`ods.nhtsa_recalls` | dlt 加载的来源快照 |
| DWD | `dwd.vehicle_detail`、`dwd.service_order_detail`、`dwd.recall_detail` | 统一车型和工单状态，解析召回日期，给工单补齐车型字段 |
| DWS | `dws.vehicle_model_summary` | 每个品牌、车型、年款一行，汇总车辆、售后工单、已完成工单费用、召回活动 |
| ADS | `ads.vehicle_aftersales_dashboard` | 给看板和 Data Agent 查询，提供工单完成率及明确标记来源的指标列 |

dbt 用 `source()` 引用 ODS 表，用 `ref()` 串联下游模型。每次刷新 ODS 后再执行 `dbt build`，重建下游表并验证数据。配置默认关闭 dbt 匿名用量统计。

先读 `dbt/models/dws/vehicle_model_summary.sql`。三份明细分别聚合到同一个粒度再关联，避免一条车辆记录被多条工单和多条召回交叉重复。对账测试从 ODS 重新计算总量，与 ADS 的车辆数、工单数、完成数、费用及召回数比较。

- 召回活动数在每个品牌、车型、年款内按 campaign 去重。同一活动可涉及多个车型。
- 完成率以全部模拟工单为分母。费用只加总已完成工单。没有工单时完成率留空。
- 这批模拟数据为每个车型生成了相同的业务量，因此三个车型均为 100 辆车、200 条工单、160 条完成。召回活动数来自真实响应。

## 官方参考

- NHTSA API：https://www.nhtsa.gov/nhtsa-datasets-and-apis
- dlt resource：https://dlthub.com/docs/general-usage/resource
- dlt DuckDB：https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb
- PostgreSQL 事务隔离：https://www.postgresql.org/docs/17/transaction-iso.html
