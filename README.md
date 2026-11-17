# Automotive Data Engineering & AI Analytics Agent

一个面向汽车质量与售后分析的端到端 **Data Engineering + Data Agent** 演示项目，将真实 NHTSA 召回 API 与 PostgreSQL 中的模拟经销商业务数据接入统一数仓，通过 dbt 建立 ODS/DWD/DWS/ADS 分层，并借助 LangGraph、DuckDB 和 Streamlit 提供可追溯的 SQL 分析、数据质检与可下载报告。

> **数据来源声明**：召回记录来自美国 NHTSA 公开 API；经销商、车辆和售后工单是 SQL 生成的模拟数据，并非福特公司内部数据。车型年款级关联**不能判断某辆车的 VIN 是否受召回影响**；本项目没有车辆保有量或销量分母，不能据此计算“故障率”。模拟工单也不是召回维修完成记录。

## 架构

```text
NHTSA Recall API ──────────────┐
                                ├─ Python extraction + snapshot ─ dlt ─ DuckDB / ODS
PostgreSQL (synthetic business) ┘                           │
                                                             ▼
                                           dbt: DWD → DWS → ADS
                                                             │
                                   ┌─────────────────────────┴────────────────────────┐
                                   ▼                                                  ▼
                           Streamlit dashboard                            LangGraph Data Agent
                       metrics / charts / QA                   NL question → SQL → validation
                                                                      ↓           ↓
                                                                  safe query → quality checks
                                                                      ↓
                                                              analysis + Markdown report
```

- **多源 ETL**：使用 `requests` 调用 NHTSA API，使用 `psycopg` 读取 PostgreSQL；包含 HTTP 重试、主键分页、同事务一致性读取、原始快照和 manifest。
- **ODS/DWD/DWS/ADS 数仓**：dlt 以 replace 模式加载 DuckDB ODS；dbt 完成字段标准化、明细关联、同粒度预聚合、指标发布及测试。
- **Data Agent**：LangGraph 生成 DuckDB SQL；只允许针对单张 ADS 表的只读 SELECT，在禁用外部访问的 DuckDB 内存库执行；失败时最多重新生成一次。固定质量检查和分析报告随后运行。
- **分析展示**：Streamlit 指标卡片、Plotly 图表、SQL/结果展示、CSV 与 Markdown 报告下载。
- **可复现**：提供原始数据快照，既可走 PostgreSQL + NHTSA 实时抽取，也可离线重放已采集的输入。

## 快速开始

需要 Python 3.11+（推荐 3.12）和 [uv](https://docs.astral.sh/uv/)；实时抽取还需要 Docker Desktop/Compose。所有命令都在**仓库根目录**运行。

```bash
git clone https://github.com/corefrank/Data-Agent.git
cd Data-Agent
uv venv --python 3.12
uv pip install -r requirements.txt
```

复制根目录的配置模板：

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

### 方式 A：真实 API + 本地 PostgreSQL（完整演示）

先确保 Docker Desktop 正在运行，然后执行：

```bash
docker compose up -d --wait
uv run python -m src build
uv run python -m src dashboard
```

`build` 会依次完成：**模拟业务库初始化 → NHTSA/PostgreSQL 抽取 → ODS 加载 → ODS 验收 → dbt build（DWD/DWS/ADS + 数据测试）**。之后 Streamlit 会在终端显示本地访问地址。

PostgreSQL 默认映射到 `localhost:5433`，仅用于本地演示。修改端口时需同步更新 `compose.yaml` 与 `.env` 中的 `PG_DSN`；修改密码时需同步更新 `POSTGRES_PASSWORD` 与 `PG_DSN`。已有 PostgreSQL 模拟数据时可使用 `build --skip-seed`。

### 方式 B：使用仓库快照重放（无 Docker、无公网数据请求）

```bash
uv run python -m src build --replay data/example_snapshot
uv run python -m src dashboard
```

此方式读取 `data/example_snapshot/` 中已保存的 NHTSA 响应和模拟业务表快照，仍会真实执行 dlt 加载、ODS 验收、dbt 建模与测试；**不代表本机完成了 PostgreSQL 或 NHTSA 在线抽取**。首次安装依赖仍需要网络。

### 使用 OpenRouter Data Agent

在 `.env` 中填写：

```dotenv
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=openai/gpt-4o-mini
```

模型名称可改为 OpenRouter 账号支持的模型。**密钥不要提交到 GitHub**。即使未填写密钥，也能浏览本地看板和质量检查；点击 Agent“开始分析”才需要模型调用。问题、SQL、查询结果与质检摘要会传给 OpenRouter；不要将含敏感信息的真实业务数据直接投入此演示环境。模型调用可能产生费用。

可尝试：
- 哪款车型年款的 NHTSA 召回活动最多？
- 对比各车型年款的模拟工单完成率。
- 哪款车型年款的已完成模拟工单费用最高？

## 统一命令行

| 命令 | 作用 |
| --- | --- |
| `uv run python -m src build` | 从初始化业务库到 dbt 指标层的完整构建 |
| `uv run python -m src build --replay data/example_snapshot` | 快照重放并完成整套构建 |
| `uv run python -m src build --skip-seed` | 跳过 PostgreSQL 模拟库初始化 |
| `uv run python -m src verify` | ODS 验收 + dbt 测试（读取最近的运行快照） |
| `uv run python -m src verify --run data/example_snapshot` | 对指定快照核验 |
| `uv run python -m src dashboard` | 启动 Streamlit 看板和 Data Agent |
| `uv run python -m src etl --replay data/example_snapshot` | 仅重放并验证 ODS，不构建下游数仓 |
| `uv run python -m src seed` | 单独初始化模拟 PostgreSQL 数据 |

运行单元测试：`uv run pytest -q`。检查数据库：`uv run python -m src.check`（或使用 `verify`）；查看 `sql/inspect_ods.sql` 中的查询。若要单独执行 dbt：`uv run dbt build --project-dir dbt --profiles-dir dbt`。

## 数仓分层与业务口径

| 层 | 实际表/模型 | 作用 |
| --- | --- | --- |
| **ODS** | `ods.dealers`, `ods.vehicles`, `ods.service_orders`, `ods.nhtsa_recalls` | 记录来源快照、原始属性、来源标识和 run_id |
| **DWD** | `dwd.vehicle_detail`, `dwd.service_order_detail`, `dwd.recall_detail` | 清洗车型和状态字段、解析日期、按键关联 |
| **DWS** | `dws.vehicle_model_summary` | 按 `make + model + model_year` 汇总车辆、工单、成本、召回活动 |
| **ADS** | `ads.vehicle_aftersales_dashboard` | 提供面向看板和 SQL Agent 的指标与完成率 |

每个车型年款先独立聚合车辆、工单和召回活动，再关联，避免多对多 JOIN 放大数据。工单完成率 = 已完成模拟工单数 / 模拟工单总数；费用仅汇总已完成模拟工单。召回活动按**车型年款内的 campaign number 去重**：跨车型加总不等于全局唯一召回活动数。

项目的真实数据与模拟数据保持明确区分：`nhtsa_recall_campaign_count` 是公开召回活动统计，`simulated_*` 指标来自模拟业务数据。

### 数据质量

- dlt/ODS 验收：来源与目标行数、主键非空唯一、外键关系、`run_id` 和 `is_synthetic`。
- dbt 测试：DWD 字段约束与关联、ADS 车型年款粒度、独立来源对账。
- Agent/看板质检：五项固定 SQL 检查；**Agent 不会自动发明新的数据质量规则**。

## 项目目录

```text
Data-Agent/
├── README.md                 # 唯一使用说明、架构与运行入口
├── requirements.txt          # ETL + dbt + Agent + Dashboard + Test 统一依赖
├── .env.example              # PostgreSQL / OpenRouter 配置模板
├── compose.yaml              # 本地 PostgreSQL
├── app.py                    # Streamlit dashboard 和报告下载
├── config/vehicles.json      # NHTSA 车型年款查询配置
├── data/example_snapshot/    # 可重放输入数据（公开 API + 模拟业务）
├── dbt/
│   ├── models/{dwd,dws,ads}/ # 数仓模型
│   ├── models/schema.yml     # 数据测试
│   └── tests/                # 汇总与粒度对账
├── sql/
│   ├── business.sql          # 模拟业务 PostgreSQL 数据
│   └── inspect_ods.sql       # ODS 查询示例
├── src/
│   ├── __main__.py           # 统一 build / verify / dashboard CLI
│   ├── seed.py               # 模拟库初始化
│   ├── extract.py            # NHTSA & PostgreSQL 抽取
│   ├── load.py               # dlt → DuckDB ODS
│   ├── pipeline.py           # 可复用 ETL 运行函数
│   ├── check.py              # ODS 验收
│   ├── agent.py              # LangGraph SQL Agent + 业务质检
│   └── common.py             # 路径、环境与 JSON 工具
└── tests/                    # 抽取、SQL 安全、Agent 与 CLI 单元测试
```

## 运行记录与设计边界

原项目在 **2026-11-17** 的验证记录中报告：PostgreSQL 6 家模拟经销商、300 辆模拟车辆、600 条模拟工单；NHTSA 三组车型年款查询分别得到 23、33、11 条召回记录；ODS 合计 973 条业务记录；dbt 建立 5 张下游表并通过 13 项数据测试。这些是原仓库记录的**既有运行结果**，不表示本次重构已在你的 Windows/Docker/OpenRouter 环境重新运行成功。

- NHTSA `recallsByVehicle` API 没有用于当前查询方式的官方分页参数，按配置逐组发请求。PostgreSQL 使用主键分页，**不是 CDC 或跨运行增量同步**。
- ODS 每次成功加载使用 `replace` 快照，不会把分批读取冒充增量同步；`data/runs/<run_id>/` 保存原始数据和 manifest。快照可重放，但不承诺跨全部源表和 dbt 发布过程的单一事务。
- SQL Agent 只查询内存库中的 `dashboard` 表，限制 SELECT、函数、数据表、外部访问和最多 200 行返回；这不是任意 SQL 执行器，也不会自动操作 ETL。
- Graph：`generate_sql → execute_sql`，失败最多修复一次，再运行固定质量检查及分析；LLM 生成报告仍应人工核对。
- 原项目未完成生产负载压测、CDC、调度、并行写入控制或真实 OpenRouter 账户验证。此次整理新增统一 CLI 和相应单元测试，但**未在本会话中重新运行真实 Docker、数据管道及模型服务**。

## 官方资料

[NHTSA API](https://www.nhtsa.gov/nhtsa-datasets-and-apis) · [dlt](https://dlthub.com/docs) · [dbt](https://docs.getdbt.com/) · [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) · [Streamlit](https://docs.streamlit.io/)
