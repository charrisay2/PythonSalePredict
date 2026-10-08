"""Đăng ký font Unicode cho reportlab.

Font mặc định của reportlab (Helvetica) KHÔNG có glyph tiếng Việt có dấu
(ví dụ "ự", "ộ", "ế" nằm ở khối Latin Extended Additional U+1EA0–U+1EF9).
Nếu không đăng ký font Unicode, các ký tự này sẽ bị mất hoặc hiện thành ô vuông
trong file PDF xuất ra.

Module này tìm font theo thứ tự ưu tiên:
1. Font nhúng sẵn trong repo: `backend/app/assets/fonts/` (ổn định khi deploy).
2. Font DejaVu đi kèm matplotlib (nếu có cài).
3. Font hệ thống (Linux: /usr/share/fonts; Windows: C:/Windows/Fonts).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FONT_NAME = "AppUnicode"
FONT_BOLD_NAME = "AppUnicode-Bold"

# Các cặp (font thường, font đậm) sẽ thử lần lượt.
_FONT_PAIRS: tuple[tuple[str, str], ...] = (
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("arial.ttf", "arialbd.ttf"),
    ("times.ttf", "timesbd.ttf"),
)

_registered = False
_result: tuple[str, str] | None = None


def _font_dirs() -> list[Path]:
    """Danh sách thư mục có thể chứa font, theo thứ tự ưu tiên."""
    directories: list[Path] = [Path(__file__).resolve().parents[1] / "assets" / "fonts"]

    try:  # matplotlib đóng gói sẵn DejaVuSans
        import matplotlib

        directories.append(Path(matplotlib.__file__).resolve().parent / "mpl-data" / "fonts" / "ttf")
    except Exception:  # pragma: no cover - matplotlib là tuỳ chọn
        pass

    directories.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/dejavu"),
            Path("/usr/share/fonts/truetype/liberation"),
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("C:/Windows/Fonts"),
        ]
    )
    return directories


def ensure_unicode_font() -> tuple[str, str] | None:
    """Đăng ký font Unicode với reportlab.

    Trả về (tên font thường, tên font đậm) đã đăng ký, hoặc None nếu không
    tìm thấy font nào phù hợp (khi đó nên quay về Helvetica).
    """
    global _registered, _result

    if _registered:
        return _result
    _registered = True

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception as exc:  # pragma: no cover
        logger.warning("Không nạp được reportlab để đăng ký font: %s", exc)
        return None

    for regular_name, bold_name in _FONT_PAIRS:
        for directory in _font_dirs():
            regular = directory / regular_name
            if not regular.exists():
                continue
            bold = directory / bold_name
            try:
                pdfmetrics.registerFont(TTFont(FONT_NAME, str(regular)))
                if bold.exists():
                    pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, str(bold)))
                    pdfmetrics.registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=FONT_BOLD_NAME)
                    _result = (FONT_NAME, FONT_BOLD_NAME)
                else:
                    pdfmetrics.registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=FONT_NAME)
                    _result = (FONT_NAME, FONT_NAME)
                logger.debug("Đã đăng ký font Unicode từ %s", regular)
                return _result
            except Exception as exc:  # pragma: no cover
                logger.warning("Không đăng ký được font %s: %s", regular, exc)

    logger.warning(
        "Không tìm thấy font Unicode; PDF có thể không hiển thị đúng tiếng Việt có dấu."
    )
    return None
