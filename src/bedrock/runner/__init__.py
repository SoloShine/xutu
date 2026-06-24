# src/bedrock/runner/__init__.py
"""LangGraph 章节管线 runner(脱离 Claude Workflow 引擎的独立 Python runner)。

确定性 StateGraph + LLM 经 API 在节点生成(非 agent runtime):控制流全在 Python,
LLM 只在 write/revise 节点出正文。信任锚 run_l2/verify-persisted 经 Python 直调,零 LLM。
纵切 v1:Boot→Write(自纠循环,cap 来自 workflow_config)→L2→Finalize。
"""
