"""Xuất báo cáo dự báo (Excel / PDF / CSV)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.core.constants import JOB_COMPLETED
from app.core.deps import DbSession, ViewerUser
from app.models import ForecastRun
from app.services.report import export_csv, export_excel, export_pdf

router = APIRouter(prefix="/reports", tags=["Báo cáo"])

MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
}

EXTENSIONS = {"xlsx": "xlsx", "pdf": "pdf", "csv": "csv"}


@router.get("/runs/{run_id}/export", summary="Tải báo cáo dự báo")
def export_report(
    run_id: int,
    user: ViewerUser,
    db: DbSession,
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf|csv)$"),
) -> Response:
    run = db.get(ForecastRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lần dự báo")
    if run.status != JOB_COMPLETED:
        raise HTTPException(status_code=400, detail="Chỉ xuất được báo cáo của lần dự báo đã hoàn thành")

    if format == "xlsx":
        content = export_excel(db, run)
    elif format == "pdf":
        content = export_pdf(db, run)
    else:
        content = export_csv(db, run)

    # Tên file có dấu tiếng Việt: gửi kèm cả bản ASCII (filename=) cho trình duyệt cũ
    # và bản mã hoá UTF-8 theo RFC 5987 (filename*=) cho trình duyệt hiện đại.
    filename = f"báo-cáo-dự-báo-{run.id}.{EXTENSIONS[format]}"
    ascii_filename = f"bao-cao-du-bao-{run.id}.{EXTENSIONS[format]}"
    disposition = (
        f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{quote(filename)}'
    )
    return Response(
        content=content,
        media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": disposition},
    )
