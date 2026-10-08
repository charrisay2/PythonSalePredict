"""Dữ liệu: nạp CSV, sinh dữ liệu mẫu, quản lý danh mục và tồn kho."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func

from app.core.deps import AnalystUser, DbSession, ViewerUser
from app.models import Channel, Holiday, Inventory, Product, Promo, Region, Sale
from app.schemas.catalog import (
    ChannelCreate,
    ChannelOut,
    HolidayCreate,
    HolidayOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    PromoCreate,
    PromoOut,
    RegionCreate,
    RegionOut,
)
from app.schemas.common import Message
from app.schemas.sales import (
    GenerateSampleRequest,
    InventoryOut,
    InventoryUpsert,
    SalesStats,
    UploadResult,
)
from app.services.data_ingest import ingest_sales_csv
from app.services.sample_data import generate_sample_data

router = APIRouter(prefix="/data", tags=["Dữ liệu"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


# ---------------------------------------------------------------------------
# Thống kê & bản ghi bán hàng
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=SalesStats, summary="Thống kê nhanh về dữ liệu bán hàng")
def sales_stats(user: ViewerUser, db: DbSession) -> SalesStats:
    row = db.query(
        func.count(Sale.id),
        func.sum(Sale.quantity),
        func.sum(Sale.revenue),
        func.min(Sale.sale_date),
        func.max(Sale.sale_date),
    ).one()
    return SalesStats(
        total_rows=int(row[0] or 0),
        total_units=float(row[1] or 0.0),
        total_revenue=float(row[2] or 0.0),
        date_start=row[3],
        date_end=row[4],
        products=db.query(func.count(Product.id)).scalar() or 0,
        regions=db.query(func.count(Region.id)).scalar() or 0,
        channels=db.query(func.count(Channel.id)).scalar() or 0,
    )


@router.get("/sales", summary="Danh sách bản ghi bán hàng (phân trang)")
def list_sales(
    user: ViewerUser,
    db: DbSession,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    start_date: str | None = None,
    end_date: str | None = None,
    product_id: int | None = None,
    region_id: int | None = None,
    channel_id: int | None = None,
) -> dict:
    query = db.query(Sale)
    if start_date:
        query = query.filter(Sale.sale_date >= start_date)
    if end_date:
        query = query.filter(Sale.sale_date <= end_date)
    if product_id:
        query = query.filter(Sale.product_id == product_id)
    if region_id:
        query = query.filter(Sale.region_id == region_id)
    if channel_id:
        query = query.filter(Sale.channel_id == channel_id)

    total = query.count()
    rows = query.order_by(Sale.sale_date.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": row.id,
                "sale_date": row.sale_date,
                "product_id": row.product_id,
                "region_id": row.region_id,
                "channel_id": row.channel_id,
                "quantity": row.quantity,
                "unit_price": row.unit_price,
                "revenue": row.revenue,
                "discount_pct": row.discount_pct,
                "is_holiday": row.is_holiday,
            }
            for row in rows
        ],
    }


@router.get("/daily-series", summary="Chuỗi sản lượng theo ngày (dùng cho biểu đồ)")
def daily_series(
    user: ViewerUser,
    db: DbSession,
    product_ids: list[int] | None = Query(default=None),
    region_ids: list[int] | None = Query(default=None),
    channel_ids: list[int] | None = Query(default=None),
    last_n: int = Query(default=180, ge=7, le=2000),
) -> dict:
    query = db.query(Sale.sale_date, func.sum(Sale.quantity).label("units"), func.sum(Sale.revenue).label("revenue"))
    if product_ids:
        query = query.filter(Sale.product_id.in_(product_ids))
    if region_ids:
        query = query.filter(Sale.region_id.in_(region_ids))
    if channel_ids:
        query = query.filter(Sale.channel_id.in_(channel_ids))
    rows = query.group_by(Sale.sale_date).order_by(Sale.sale_date).all()
    tail = rows[-last_n:]
    return {
        "items": [{"ds": row.sale_date, "y": round(float(row.units or 0), 2), "revenue": round(float(row.revenue or 0), 2)} for row in tail]
    }


# ---------------------------------------------------------------------------
# Nạp dữ liệu
# ---------------------------------------------------------------------------
@router.post("/upload", response_model=UploadResult, summary="Nạp dữ liệu bán hàng từ CSV")
async def upload_sales(user: AnalystUser, db: DbSession, file: UploadFile = File(...)) -> UploadResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .csv")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File rỗng")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File quá lớn (tối đa 25MB)")

    result = ingest_sales_csv(db, content)
    if result["rows_inserted"] == 0:
        raise HTTPException(
            status_code=422,
            detail={"message": "Không nạp được dòng nào", "errors": result["errors"]},
        )
    return UploadResult(**result)


@router.post("/generate-sample", response_model=UploadResult, summary="Sinh bộ dữ liệu bán hàng mẫu")
def generate_sample(payload: GenerateSampleRequest, user: AnalystUser, db: DbSession) -> UploadResult:
    stats = generate_sample_data(
        db,
        days=payload.days,
        products=payload.products,
        regions=payload.regions,
        channels=payload.channels,
        seed=payload.seed,
        reset=payload.reset,
    )
    return UploadResult(
        rows_received=stats["sales_rows"],
        rows_inserted=stats["sales_rows"],
        rows_skipped=0,
        errors=[],
        date_start=stats["date_start"],
        date_end=stats["date_end"],
    )


# ---------------------------------------------------------------------------
# Danh mục: Region
# ---------------------------------------------------------------------------
@router.get("/regions", response_model=list[RegionOut])
def list_regions(user: ViewerUser, db: DbSession) -> list[RegionOut]:
    return [RegionOut.model_validate(row) for row in db.query(Region).order_by(Region.name).all()]


@router.post("/regions", response_model=RegionOut, status_code=status.HTTP_201_CREATED)
def create_region(payload: RegionCreate, user: AnalystUser, db: DbSession) -> RegionOut:
    if db.query(Region).filter((Region.name == payload.name) | (Region.code == payload.code)).first():
        raise HTTPException(status_code=409, detail="Khu vực (tên hoặc mã) đã tồn tại")
    row = Region(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return RegionOut.model_validate(row)


@router.delete("/regions/{region_id}", response_model=Message)
def delete_region(region_id: int, user: AnalystUser, db: DbSession) -> Message:
    row = db.get(Region, region_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy khu vực")
    if db.query(Sale).filter(Sale.region_id == region_id).first():
        raise HTTPException(status_code=409, detail="Khu vực đang có dữ liệu bán hàng, không thể xóa")
    db.delete(row)
    db.commit()
    return Message(message="Đã xóa khu vực")


# ---------------------------------------------------------------------------
# Danh mục: Channel
# ---------------------------------------------------------------------------
@router.get("/channels", response_model=list[ChannelOut])
def list_channels(user: ViewerUser, db: DbSession) -> list[ChannelOut]:
    return [ChannelOut.model_validate(row) for row in db.query(Channel).order_by(Channel.name).all()]


@router.post("/channels", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
def create_channel(payload: ChannelCreate, user: AnalystUser, db: DbSession) -> ChannelOut:
    if db.query(Channel).filter((Channel.name == payload.name) | (Channel.code == payload.code)).first():
        raise HTTPException(status_code=409, detail="Kênh bán (tên hoặc mã) đã tồn tại")
    row = Channel(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ChannelOut.model_validate(row)


@router.delete("/channels/{channel_id}", response_model=Message)
def delete_channel(channel_id: int, user: AnalystUser, db: DbSession) -> Message:
    row = db.get(Channel, channel_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh bán")
    if db.query(Sale).filter(Sale.channel_id == channel_id).first():
        raise HTTPException(status_code=409, detail="Kênh bán đang có dữ liệu, không thể xóa")
    db.delete(row)
    db.commit()
    return Message(message="Đã xóa kênh bán")


# ---------------------------------------------------------------------------
# Danh mục: Product
# ---------------------------------------------------------------------------
@router.get("/products", response_model=list[ProductOut])
def list_products(user: ViewerUser, db: DbSession, only_active: bool = False) -> list[ProductOut]:
    query = db.query(Product)
    if only_active:
        query = query.filter(Product.is_active.is_(True))
    return [ProductOut.model_validate(row) for row in query.order_by(Product.sku).all()]


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, user: AnalystUser, db: DbSession) -> ProductOut:
    if db.query(Product).filter(Product.sku == payload.sku).first():
        raise HTTPException(status_code=409, detail="SKU đã tồn tại")
    row = Product(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ProductOut.model_validate(row)


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, user: AnalystUser, db: DbSession) -> ProductOut:
    row = db.get(Product, product_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return ProductOut.model_validate(row)


@router.delete("/products/{product_id}", response_model=Message)
def delete_product(product_id: int, user: AnalystUser, db: DbSession) -> Message:
    row = db.get(Product, product_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    row.is_active = False
    db.commit()
    return Message(message=f"Đã ngừng hoạt động sản phẩm {row.sku}")


# ---------------------------------------------------------------------------
# Danh mục: Holiday
# ---------------------------------------------------------------------------
@router.get("/holidays", response_model=list[HolidayOut])
def list_holidays(user: ViewerUser, db: DbSession) -> list[HolidayOut]:
    return [
        HolidayOut.model_validate(row)
        for row in db.query(Holiday).order_by(Holiday.holiday_date).all()
    ]


@router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def create_holiday(payload: HolidayCreate, user: AnalystUser, db: DbSession) -> HolidayOut:
    row = Holiday(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return HolidayOut.model_validate(row)


@router.delete("/holidays/{holiday_id}", response_model=Message)
def delete_holiday(holiday_id: int, user: AnalystUser, db: DbSession) -> Message:
    row = db.get(Holiday, holiday_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy ngày lễ")
    db.delete(row)
    db.commit()
    return Message(message="Đã xóa ngày lễ")


# ---------------------------------------------------------------------------
# Danh mục: Promo
# ---------------------------------------------------------------------------
@router.get("/promos", response_model=list[PromoOut])
def list_promos(user: ViewerUser, db: DbSession) -> list[PromoOut]:
    return [PromoOut.model_validate(row) for row in db.query(Promo).order_by(Promo.start_date).all()]


@router.post("/promos", response_model=PromoOut, status_code=status.HTTP_201_CREATED)
def create_promo(payload: PromoCreate, user: AnalystUser, db: DbSession) -> PromoOut:
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="Ngày kết thúc phải sau ngày bắt đầu")
    row = Promo(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return PromoOut.model_validate(row)


@router.delete("/promos/{promo_id}", response_model=Message)
def delete_promo(promo_id: int, user: AnalystUser, db: DbSession) -> Message:
    row = db.get(Promo, promo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy khuyến mãi")
    db.delete(row)
    db.commit()
    return Message(message="Đã xóa khuyến mãi")


# ---------------------------------------------------------------------------
# Tồn kho
# ---------------------------------------------------------------------------
@router.get("/inventory", response_model=list[InventoryOut])
def list_inventory(user: ViewerUser, db: DbSession) -> list[InventoryOut]:
    return [InventoryOut.model_validate(row) for row in db.query(Inventory).order_by(Inventory.id).all()]


@router.post("/inventory", response_model=InventoryOut, summary="Cập nhật / tạo bản ghi tồn kho")
def upsert_inventory(payload: InventoryUpsert, user: AnalystUser, db: DbSession) -> InventoryOut:
    row = (
        db.query(Inventory)
        .filter(Inventory.product_id == payload.product_id, Inventory.region_id == payload.region_id)
        .first()
    )
    if row is None:
        row = Inventory(**payload.model_dump())
        db.add(row)
    else:
        row.on_hand_qty = payload.on_hand_qty
        row.safety_stock = payload.safety_stock
        row.incoming_qty = payload.incoming_qty
    db.commit()
    db.refresh(row)
    return InventoryOut.model_validate(row)
