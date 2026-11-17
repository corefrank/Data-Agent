"""Data Agent: 生成 SQL → 校验与执行 → 失败时修复一次 → 撰写分析。"""
import json
import os
import re
from typing import TypedDict

import duckdb
import requests
import sqlglot
from sqlglot import exp
from langgraph.graph import END, START, StateGraph

from .common import ROOT, load_dotenv

load_dotenv(ROOT / '.env')
SCHEMA = '''唯一可查询表 dashboard，字段：
make VARCHAR, model VARCHAR, model_year INTEGER,
simulated_vehicle_count INTEGER, simulated_service_order_count INTEGER,
simulated_completed_order_count INTEGER, simulated_completion_pct DOUBLE,
simulated_completed_service_cost DECIMAL, nhtsa_recall_campaign_count INTEGER。
一行代表品牌、车型、年款。车辆和工单数据是模拟数据，召回活动来自真实 NHTSA，
召回数是该车型年款内去重活动数，不能判断单车是否受影响。完成率是百分数。'''


def call_model(messages):
    key = os.getenv('OPENROUTER_API_KEY', '').strip()
    if not key:
        raise ValueError('请在项目根目录 .env 设置 OPENROUTER_API_KEY')
    response = requests.post('https://openrouter.ai/api/v1/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={'model': os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o-mini'),
              'messages': messages, 'temperature': 0, 'max_tokens': 1000}, timeout=(10, 60))
    response.raise_for_status()
    content = response.json()['choices'][0]['message']['content']
    if not isinstance(content, str) or not content.strip():
        raise ValueError('模型未返回文本，请更换模型或检查 OpenRouter 配置')
    return content.strip()


def validate_sql(sql):
    sql = re.sub(r'^```(?:sql)?\s*|\s*```$', '', sql.strip(), flags=re.I)
    statements = sqlglot.parse(sql, read='duckdb')
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError('只允许一条 SELECT 查询')
    tree = statements[0]
    # 表函数、文件读取、系统表、CTE 都不用于本项目。
    if tree.args.get('with_') or any(not isinstance(t.this, exp.Identifier) or
            t.name.lower() != 'dashboard' or t.db or t.catalog for t in tree.find_all(exp.Table)):
        raise ValueError('只允许查询 dashboard 表，不支持 CTE 或外部表')
    if not list(tree.find_all(exp.Table)):
        raise ValueError('查询必须使用 dashboard 表')
    if any(isinstance(n, (exp.Command, exp.DDL, exp.DML, exp.Into, exp.Pragma)) for n in tree.walk()):
        raise ValueError('只允许只读查询')
    # 只放行分析所需函数，禁止可能读取外部资源的函数。
    allowed = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ROUND', 'COALESCE', 'NULLIF', 'CAST', 'LOWER', 'UPPER', 'ABS'}
    for fn in tree.find_all(exp.Func):
        name = fn.name.upper() if isinstance(fn, exp.Anonymous) else fn.sql_name().upper()
        if name not in allowed:
            raise ValueError(f'函数未允许: {name}')
    return tree.sql(dialect='duckdb')


def run_sql(sql):
    sql = validate_sql(sql)
    # 只将 ADS 数据复制进内存，模型 SQL 无法访问项目的其他表或外部文件。
    with duckdb.connect(str(ROOT / 'data/warehouse.duckdb'), read_only=True) as source:
        data = source.execute('SELECT * FROM ads.vehicle_aftersales_dashboard').fetchdf()
    with duckdb.connect(':memory:', config={'enable_external_access': 'false', 'threads': '1', 'memory_limit': '256MB'}) as conn:
        conn.register('input_data', data)
        conn.execute('CREATE TABLE dashboard AS SELECT * FROM input_data')
        conn.unregister('input_data')
        result = conn.execute(f'SELECT * FROM ({sql}) AS query_result LIMIT 201').fetchdf()
    truncated = len(result) > 200
    return sql, result.head(200), truncated


def quality_checks():
    with duckdb.connect(str(ROOT / 'data/warehouse.duckdb'), read_only=True) as c:
        checks = {
            'ADS 车型粒度重复': c.execute('SELECT count(*) FROM (SELECT make,model,model_year FROM ads.vehicle_aftersales_dashboard GROUP BY ALL HAVING count(*)>1)').fetchone()[0],
            '车辆主键为空或重复': c.execute('SELECT count(*) - count(DISTINCT vehicle_id) FROM ods.vehicles').fetchone()[0],
            '工单缺少车辆': c.execute('SELECT count(*) FROM ods.service_orders o LEFT JOIN ods.vehicles v USING(vehicle_id) WHERE v.vehicle_id IS NULL').fetchone()[0],
            '召回日期解析失败': c.execute('SELECT count(*) FROM dwd.recall_detail WHERE report_received_date IS NULL').fetchone()[0],
            '工单总数对账差值': c.execute('SELECT abs((SELECT count(*) FROM ods.service_orders)-(SELECT coalesce(sum(simulated_service_order_count),0) FROM ads.vehicle_aftersales_dashboard))').fetchone()[0],
        }
    return checks


class AgentState(TypedDict, total=False):
    question: str
    sql: str
    error: str
    attempts: int
    rows: list
    columns: list
    truncated: bool
    answer: str
    checks: dict


def generate(state):
    correction = f"上次执行失败：{state.get('error')}。上一条 SQL：{state.get('sql')}。请修正。" if state.get('error') else ''
    sql = call_model([{'role':'system','content': '你是 DuckDB SQL 专家。只输出一条 SELECT SQL，不要解释。只允许查询 dashboard 表，不要使用 CTE。'+SCHEMA},
                      {'role':'user','content': state['question']+'\n'+correction}])
    return {'sql': sql, 'attempts': state.get('attempts', 0)+1}


def execute(state):
    try:
        sql, frame, truncated = run_sql(state['sql'])
        return {'sql': sql, 'rows': json.loads(frame.to_json(orient='records', date_format='iso')), 'columns': list(frame.columns), 'truncated': truncated, 'error': ''}
    except Exception as e:
        return {'error': str(e)}


def route(state):
    return 'repair' if state.get('error') and state['attempts'] < 2 else ('failed' if state.get('error') else 'answer')


def analyze(state):
    checks = quality_checks()
    prompt = f"问题：{state['question']}\nSQL：{state['sql']}\n结果：{json.dumps(state['rows'], ensure_ascii=False)}\n结果截断：{state['truncated']}\n质检异常计数：{checks}"
    answer = call_model([{'role':'system','content':'根据提供的查询结果用中文回答，列出关键数字和局限，不要虚构。数据定义：'+SCHEMA}, {'role':'user','content':prompt}])
    return {'answer':answer, 'checks':checks}


def graph():
    builder = StateGraph(AgentState)
    builder.add_node('generate_sql', generate)
    builder.add_node('execute_sql', execute)
    builder.add_node('analyze', analyze)
    builder.add_edge(START, 'generate_sql')
    builder.add_edge('generate_sql', 'execute_sql')
    builder.add_conditional_edges('execute_sql', route, {'repair':'generate_sql', 'answer':'analyze', 'failed':END})
    builder.add_edge('analyze', END)
    return builder.compile()


def run_agent(question):
    return graph().invoke({'question': question, 'attempts': 0})
