import json
from datetime import datetime

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

from src.agent import quality_checks, run_agent
from src.common import ROOT

st.set_page_config(page_title='车辆与售后数据分析', layout='wide')
st.title('车辆与售后数据分析')
st.caption('车辆与售后工单为模拟数据，召回信息来自 NHTSA。车型年款关联不能判断单辆车是否受召回影响。')

try:
    with duckdb.connect(str(ROOT / 'data/warehouse.duckdb'), read_only=True) as connection:
        data = connection.execute('SELECT * FROM ads.vehicle_aftersales_dashboard ORDER BY model').fetchdf()
    checks = quality_checks()
except Exception as error:
    st.error(f'读取数仓失败，请先运行 dbt build。{error}')
    st.stop()

chart, table, agent_tab = st.tabs(['指标看板', '数据质检', 'Data Agent'])
with chart:
    if data.empty:
        st.info('ADS 当前没有数据。')
    else:
        a, b, c = st.columns(3)
        a.metric('模拟车辆数', f"{data.simulated_vehicle_count.sum():,}")
        b.metric('模拟工单数', f"{data.simulated_service_order_count.sum():,}")
        c.metric('车型年款召回活动数之和', f"{data.nhtsa_recall_campaign_count.sum():,}", help='同一召回活动可能涉及多个车型，此值不是全局去重后的活动数。')
        st.plotly_chart(px.bar(data, x='model', y='nhtsa_recall_campaign_count', color='model', title='各车型年款的 NHTSA 召回活动数'), use_container_width=True)
        st.dataframe(data, use_container_width=True, hide_index=True)
        st.download_button('下载指标 CSV', data.to_csv(index=False).encode('utf-8-sig'), 'vehicle_metrics.csv', 'text/csv')
with table:
    results = pd.DataFrame([{'检查': name, '异常数': value, '结果': '通过' if value == 0 else '异常'} for name, value in checks.items()])
    st.dataframe(results, use_container_width=True, hide_index=True)
    st.caption('这里是轻量业务质检。完整 dbt 测试请运行 dbt build。')
with agent_tab:
    question = st.text_input('请输入分析问题', value='哪款车型的召回活动最多？对比各车型的模拟工单完成率。')
    if st.button('开始分析', type='primary'):
        st.session_state.pop('agent_result', None)
        if not question.strip():
            st.warning('请输入问题。')
        else:
            with st.spinner('生成 SQL、执行查询并撰写报告中……'):
                try:
                    result = run_agent(question)
                    if result.get('error'):
                        st.error('SQL 执行失败：'+result['error'])
                        st.code(result.get('sql', ''), language='sql')
                    else:
                        st.session_state['agent_result'] = result
                except Exception as error:
                    st.error(f'分析失败，请检查 API Key、模型或网络：{error}')
    if 'agent_result' in st.session_state:
        result = st.session_state['agent_result']
        st.markdown(result['answer'])
        st.dataframe(pd.DataFrame(result['rows'], columns=result['columns']), use_container_width=True, hide_index=True)
        if result['truncated']:
            st.warning('结果超过 200 行，仅展示并分析前 200 行。')
        with st.expander('查看 SQL 与质检'):
            st.code(result['sql'], language='sql')
            st.json(result['checks'])
        report = f"# 数据分析报告\n\n生成时间：{datetime.now().isoformat(timespec='seconds')}\n\n## 问题\n{result['question']}\n\n## 分析\n{result['answer']}\n\n## SQL\n```sql\n{result['sql']}\n```\n\n## 查询结果\n```json\n{json.dumps(result['rows'], ensure_ascii=False, indent=2)}\n```\n\n## 数据质检异常数\n```json\n{json.dumps(result['checks'], ensure_ascii=False, indent=2)}\n```\n\n结果截断：{result['truncated']}。车辆与工单为模拟数据，召回为 NHTSA 公开数据。\n"
        st.download_button('下载分析报告 Markdown', report.encode('utf-8'), 'analysis_report.md', 'text/markdown')
