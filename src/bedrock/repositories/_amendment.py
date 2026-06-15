# src/bedrock/repositories/_amendment.py
"""amendment 记录助手：包 governance.add_amendment，best-effort（写失败仅记日志，不阻断主写）。"""
import logging
from src.bedrock.repositories.governance import add_amendment

_log = logging.getLogger(__name__)


def record_amendment(conn, entity_type, entity_id, field, old, new):
    """记一条修正。失败 best-effort（本地单用户，审计完整性不阻断可用性）。

    governance.add_amendment 真实签名：(conn, entity_type, entity_id, field, new, old=None, ...)
    即 new 在 old 之前。
    """
    try:
        add_amendment(conn, entity_type=entity_type, entity_id=entity_id,
                      field=field, new=str(new), old=(None if old is None else str(old)))
    except Exception as e:
        _log.warning("amendment 记录失败 %s/%s/%s: %s", entity_type, entity_id, field, e)
