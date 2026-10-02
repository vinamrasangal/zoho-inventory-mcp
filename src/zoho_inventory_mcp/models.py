"""Agent-facing response models.

Zoho payloads are large (100+ fields per sales order). These models keep only what an agent
needs to answer merchant questions, which keeps responses small and the schemas self-describing.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _address(raw: dict[str, Any] | None) -> str | None:
    if not raw:
        return None
    parts = [raw.get(k) for k in ("address", "street2", "city", "state", "zip", "country")]
    joined = ", ".join(str(p) for p in parts if p)
    return joined or None


class Page(BaseModel, Generic[T]):
    results: list[T]
    page: int
    per_page: int
    has_more: bool = Field(description="True if another page exists; call again with page=next_page.")
    next_page: int | None = None


class WarehouseStock(BaseModel):
    warehouse_id: str | None = None
    warehouse_name: str
    stock_on_hand: float | None = None
    available_stock: float | None = None


class ItemSummary(BaseModel):
    item_id: str
    name: str
    sku: str | None = None
    status: str | None = None
    unit: str | None = None
    rate: float | None = Field(default=None, description="Selling price per unit.")
    stock_on_hand: float | None = Field(default=None, description="Physical stock across warehouses.")
    available_stock: float | None = Field(
        default=None, description="Stock on hand minus quantities committed to open orders."
    )
    reorder_level: float | None = None
    is_low_stock: bool = Field(description="available_stock is at or below a non-zero reorder_level.")

    @classmethod
    def from_zoho(cls, raw: dict[str, Any]) -> ItemSummary:
        available = _num(raw.get("available_stock"))
        reorder = _num(raw.get("reorder_level"))
        return cls(
            item_id=str(raw["item_id"]),
            name=raw.get("name", ""),
            sku=raw.get("sku") or None,
            status=raw.get("status"),
            unit=raw.get("unit") or None,
            rate=_num(raw.get("rate")),
            stock_on_hand=_num(raw.get("stock_on_hand")),
            available_stock=available,
            reorder_level=reorder,
            is_low_stock=bool(reorder and available is not None and available <= reorder),
        )


class ItemDetail(ItemSummary):
    description: str | None = None
    purchase_rate: float | None = None
    category: str | None = None
    brand: str | None = None
    hsn_or_sac: str | None = None
    warehouses: list[WarehouseStock] = []

    @classmethod
    def from_zoho(cls, raw: dict[str, Any]) -> ItemDetail:
        base = ItemSummary.from_zoho(raw).model_dump()
        return cls(
            **base,
            description=raw.get("description") or None,
            purchase_rate=_num(raw.get("purchase_rate")),
            category=raw.get("category_name") or None,
            brand=raw.get("brand") or None,
            hsn_or_sac=raw.get("hsn_or_sac") or None,
            warehouses=[
                WarehouseStock(
                    warehouse_id=w.get("warehouse_id"),
                    warehouse_name=w.get("warehouse_name", ""),
                    stock_on_hand=_num(w.get("warehouse_stock_on_hand")),
                    available_stock=_num(w.get("warehouse_available_stock")),
                )
                for w in raw.get("warehouses", [])
            ],
        )


class LowStockReport(BaseModel):
    items: list[ItemSummary] = Field(description="Low-stock items, most urgent (largest shortfall) first.")
    scanned_items: int
    truncated: bool = Field(description="True if the catalogue was larger than the scan limit.")


class LineItem(BaseModel):
    item_id: str | None = None
    name: str
    sku: str | None = None
    quantity: float | None = None
    rate: float | None = None
    total: float | None = None
    quantity_shipped: float | None = None


class SalesOrderSummary(BaseModel):
    salesorder_id: str
    salesorder_number: str
    date: str | None = None
    shipment_date: str | None = None
    reference_number: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    status: str | None = None
    invoiced_status: str | None = None
    paid_status: str | None = None
    shipped_status: str | None = None
    total: float | None = None
    currency_code: str | None = None

    @classmethod
    def from_zoho(cls, raw: dict[str, Any]) -> SalesOrderSummary:
        return cls(
            salesorder_id=str(raw["salesorder_id"]),
            salesorder_number=raw.get("salesorder_number", ""),
            date=raw.get("date") or None,
            shipment_date=raw.get("shipment_date") or None,
            reference_number=raw.get("reference_number") or None,
            customer_id=raw.get("customer_id"),
            customer_name=raw.get("customer_name"),
            status=raw.get("status") or raw.get("order_status"),
            invoiced_status=raw.get("invoiced_status") or None,
            paid_status=raw.get("paid_status") or None,
            shipped_status=raw.get("shipped_status") or None,
            total=_num(raw.get("total")),
            currency_code=raw.get("currency_code"),
        )


class SalesOrderDetail(SalesOrderSummary):
    line_items: list[LineItem] = []
    sub_total: float | None = None
    tax_total: float | None = None
    shipping_charge: float | None = None
    delivery_method: str | None = None
    salesperson_name: str | None = None
    shipping_address: str | None = None
    notes: str | None = None

    @classmethod
    def from_zoho(cls, raw: dict[str, Any]) -> SalesOrderDetail:
        base = SalesOrderSummary.from_zoho(raw).model_dump()
        return cls(
            **base,
            line_items=[
                LineItem(
                    item_id=li.get("item_id"),
                    name=li.get("name", ""),
                    sku=li.get("sku") or None,
                    quantity=_num(li.get("quantity")),
                    rate=_num(li.get("rate")),
                    total=_num(li.get("item_total")),
                    quantity_shipped=_num(li.get("quantity_shipped")),
                )
                for li in raw.get("line_items", [])
            ],
            sub_total=_num(raw.get("sub_total")),
            tax_total=_num(raw.get("tax_total")),
            shipping_charge=_num(raw.get("shipping_charge")),
            delivery_method=raw.get("delivery_method") or None,
            salesperson_name=raw.get("salesperson_name") or None,
            shipping_address=_address(raw.get("shipping_address")),
            notes=raw.get("notes") or None,
        )


class CustomerSummary(BaseModel):
    customer_id: str
    name: str
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None
    outstanding_receivable: float | None = Field(default=None, description="Unpaid invoice amount.")
    currency_code: str | None = None

    @classmethod
    def from_zoho(cls, raw: dict[str, Any]) -> CustomerSummary:
        return cls(
            customer_id=str(raw["contact_id"]),
            name=raw.get("contact_name", ""),
            company_name=raw.get("company_name") or None,
            email=raw.get("email") or None,
            phone=raw.get("phone") or raw.get("mobile") or None,
            status=raw.get("status"),
            outstanding_receivable=_num(raw.get("outstanding_receivable_amount")),
            currency_code=raw.get("currency_code"),
        )


class CustomerDetail(CustomerSummary):
    billing_address: str | None = None
    shipping_address: str | None = None
    gst_no: str | None = None
    created_time: str | None = None

    @classmethod
    def from_zoho(cls, raw: dict[str, Any]) -> CustomerDetail:
        base = CustomerSummary.from_zoho(raw).model_dump()
        return cls(
            **base,
            billing_address=_address(raw.get("billing_address")),
            shipping_address=_address(raw.get("shipping_address")),
            gst_no=raw.get("gst_no") or None,
            created_time=raw.get("created_time") or None,
        )


class ItemPage(Page[ItemSummary]):
    pass


class SalesOrderPage(Page[SalesOrderSummary]):
    pass


class CustomerPage(Page[CustomerSummary]):
    pass


class ConnectionStatus(BaseModel):
    connected: bool
    organization_id: str | None = None
    organization_name: str | None = None
    api_domain: str | None = None
    access_token_expires_in_seconds: int | None = None
    granted_scopes: str | None = None
    rate_limits: dict[str, Any] = {}
    message: str | None = None
