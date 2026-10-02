"""Deterministic demo dataset: an Indian D2C tea & spice brand ("Kesariya Foods")."""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from typing import Any

ORG_ID = "60012345678"
ORG_NAME = "Kesariya Foods Pvt Ltd"
WAREHOUSES = [("4600000000001", "Bengaluru Fulfilment Centre"), ("4600000000002", "Mumbai Warehouse")]

CATALOGUE = [
    ("Assam Breakfast Tea 250g", "TEA-ASM-250", "pcs", 349, "Tea", "Loose-leaf CTC Assam, malty and strong."),
    ("Assam Breakfast Tea 1kg", "TEA-ASM-1KG", "pcs", 1199, "Tea", "Bulk pack of our breakfast blend."),
    ("Darjeeling First Flush 100g", "TEA-DJF-100", "pcs", 699, "Tea", "Spring harvest, muscatel notes."),
    ("Nilgiri Frost Tea 250g", "TEA-NLG-250", "pcs", 399, "Tea", "Bright, brisk winter-frost tea."),
    ("Masala Chai Blend 250g", "TEA-MSL-250", "pcs", 379, "Tea", "Assam CTC with cardamom, ginger, clove."),
    ("Masala Chai Blend 500g", "TEA-MSL-500", "pcs", 699, "Tea", "Family pack of masala chai."),
    ("Kashmiri Kahwa 100g", "TEA-KHW-100", "pcs", 549, "Tea", "Green tea with saffron and almonds."),
    ("Tulsi Green Tea 25 bags", "TEA-TUL-25", "box", 249, "Tea", "Holy basil and green tea, pyramid bags."),
    ("Lemongrass Ginger Tea 25 bags", "TEA-LMG-25", "box", 249, "Tea", "Caffeine-free herbal infusion."),
    ("Kesar Saffron 1g", "SPC-SAF-1G", "pcs", 449, "Spices", "Grade-1 Kashmiri mongra saffron."),
    ("Kesar Saffron 5g", "SPC-SAF-5G", "pcs", 1999, "Spices", "Grade-1 Kashmiri mongra saffron."),
    ("Green Cardamom 100g", "SPC-CRD-100", "pcs", 399, "Spices", "8mm bold Idukki cardamom."),
    ("Black Pepper Whole 200g", "SPC-PEP-200", "pcs", 299, "Spices", "Malabar garbled pepper."),
    ("Kashmiri Chilli Powder 200g", "SPC-KCP-200", "pcs", 189, "Spices", "Deep colour, mild heat."),
    (
        "Turmeric Powder Lakadong 200g",
        "SPC-TUR-200",
        "pcs",
        229,
        "Spices",
        "High-curcumin Lakadong turmeric.",
    ),
    ("Garam Masala 100g", "SPC-GRM-100", "pcs", 179, "Spices", "Stone-ground house blend."),
    ("Kitchen King Masala 100g", "SPC-KKM-100", "pcs", 169, "Spices", "All-purpose curry masala."),
    ("Cumin Seeds 200g", "SPC-CMN-200", "pcs", 199, "Spices", "Unjha cumin, machine cleaned."),
    ("Cinnamon Sticks 100g", "SPC-CIN-100", "pcs", 249, "Spices", "Ceylon true cinnamon quills."),
    ("Cloves Whole 50g", "SPC-CLV-50", "pcs", 179, "Spices", "Hand-picked Kerala cloves."),
    ("Star Anise 50g", "SPC-STA-50", "pcs", 149, "Spices", "Whole star anise pods."),
    ("Hing Compounded 50g", "SPC-HNG-50", "pcs", 219, "Spices", "Strong asafoetida."),
    ("Biryani Masala 100g", "SPC-BRY-100", "pcs", 189, "Spices", "Hyderabadi-style blend."),
    ("Sambar Powder 200g", "SPC-SMB-200", "pcs", 159, "Spices", "Chettinad-style sambar powder."),
    ("Chai Lovers Gift Box", "GFT-CHAI-01", "box", 1499, "Gift Boxes", "Four teas, a strainer and a mug."),
    ("Spice Route Gift Box", "GFT-SPCE-01", "box", 1799, "Gift Boxes", "Six whole spices in glass jars."),
    ("Diwali Hamper Premium", "GFT-DIW-01", "box", 2999, "Gift Boxes", "Saffron, kahwa, dry fruits, diya."),
    ("Corporate Gift Box (min 25)", "GFT-CORP-25", "box", 899, "Gift Boxes", "Branded tea and spice box."),
    ("Brass Tea Strainer", "ACC-STR-01", "pcs", 299, "Accessories", "Handmade brass strainer."),
    ("Kulhad Set of 6", "ACC-KLH-06", "set", 399, "Accessories", "Terracotta chai cups."),
    ("Copper Kettle 1.2L", "ACC-KTL-12", "pcs", 1899, "Accessories", "Hammered copper with brass handle."),
    ("Glass Spice Jars Set of 4", "ACC-JAR-04", "set", 599, "Accessories", "Airtight borosilicate jars."),
    ("Jaggery Powder 500g", "PNT-JAG-500", "pcs", 149, "Pantry", "Chemical-free sugarcane jaggery."),
    ("A2 Ghee 500ml", "PNT-GHE-500", "pcs", 899, "Pantry", "Bilona-churned Gir cow ghee."),
    ("Wild Forest Honey 500g", "PNT-HNY-500", "pcs", 549, "Pantry", "Raw unprocessed honey."),
    ("Mixed Dry Fruits 250g", "PNT-DRF-250", "pcs", 649, "Pantry", "Almonds, cashews, raisins, pistachios."),
    ("Masala Chai Blend 250g (Old Pack)", "TEA-MSL-250-OLD", "pcs", 349, "Tea", "Discontinued packaging."),
]

FIRST = [
    "Aarav",
    "Ananya",
    "Vihaan",
    "Diya",
    "Arjun",
    "Ishita",
    "Kabir",
    "Meera",
    "Rohan",
    "Saanvi",
    "Aditya",
    "Priya",
    "Karan",
    "Neha",
    "Siddharth",
    "Riya",
    "Varun",
    "Kavya",
    "Nikhil",
    "Tara",
]
LAST = ["Sharma", "Iyer", "Reddy", "Patel", "Nair", "Gupta", "Menon", "Kapoor", "Joshi", "Rao"]
BUSINESSES = [
    ("Chaayos Retail LLP", "Bengaluru", "Karnataka", "29"),
    ("Third Wave Corporate Gifting", "Mumbai", "Maharashtra", "27"),
    ("Blue Tokai Cafe Supplies", "New Delhi", "Delhi", "07"),
    ("Hotel Sea Breeze", "Kochi", "Kerala", "32"),
    ("Spice Bazaar Exports", "Chennai", "Tamil Nadu", "33"),
]
CITIES = [
    ("Bengaluru", "Karnataka", "560034"),
    ("Mumbai", "Maharashtra", "400050"),
    ("Pune", "Maharashtra", "411001"),
    ("Hyderabad", "Telangana", "500081"),
    ("Chennai", "Tamil Nadu", "600017"),
    ("Jaipur", "Rajasthan", "302001"),
    ("Kolkata", "West Bengal", "700019"),
    ("Gurugram", "Haryana", "122002"),
]

AS_OF = dt.date(2026, 9, 30)


@dataclass
class Dataset:
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    contacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    salesorders: dict[str, dict[str, Any]] = field(default_factory=dict)
    organizations: list[dict[str, Any]] = field(default_factory=list)


def _address(rng: random.Random, city: str, state: str, zip_code: str) -> dict[str, str]:
    street = rng.choice(["MG Road", "Linking Road", "Park Street", "2nd Cross", "Main Road"])
    return {
        "address": f"{rng.randint(1, 450)}, {street}",
        "street2": "",
        "city": city,
        "state": state,
        "zip": zip_code,
        "country": "India",
    }


def build_dataset(seed: int = 42) -> Dataset:
    rng = random.Random(seed)
    ds = Dataset()
    ds.organizations = [
        {
            "organization_id": ORG_ID,
            "name": ORG_NAME,
            "currency_code": "INR",
            "time_zone": "Asia/Calcutta",
            "is_default_org": True,
        }
    ]

    for i, (name, sku, unit, rate, category, description) in enumerate(CATALOGUE):
        item_id = f"2400000000{i + 1:05d}"
        discontinued = sku.endswith("-OLD")
        reorder = 0 if discontinued else rng.choice([10, 15, 20, 25, 30, 40, 50])
        roll = rng.random()
        if discontinued:
            on_hand = rng.randint(0, 5)
        elif roll < 0.22:
            on_hand = rng.randint(0, reorder)
        else:
            on_hand = rng.randint(reorder + 5, reorder * 8)
        committed = min(on_hand, rng.randint(0, 6))
        split = rng.uniform(0.4, 0.8)
        bl = round(on_hand * split)
        bl_committed = min(bl, committed)
        warehouses = [
            {
                "warehouse_id": WAREHOUSES[0][0],
                "warehouse_name": WAREHOUSES[0][1],
                "is_primary": True,
                "warehouse_stock_on_hand": bl,
                "warehouse_available_stock": bl - bl_committed,
            },
            {
                "warehouse_id": WAREHOUSES[1][0],
                "warehouse_name": WAREHOUSES[1][1],
                "is_primary": False,
                "warehouse_stock_on_hand": on_hand - bl,
                "warehouse_available_stock": on_hand - bl - (committed - bl_committed),
            },
        ]
        ds.items[item_id] = {
            "item_id": item_id,
            "name": name,
            "sku": sku,
            "unit": unit,
            "status": "inactive" if discontinued else "active",
            "description": description,
            "rate": rate,
            "purchase_rate": round(rate * 0.55, 2),
            "item_type": "inventory",
            "product_type": "goods",
            "category_name": category,
            "brand": "Kesariya",
            "hsn_or_sac": "0902" if category == "Tea" else "0910",
            "stock_on_hand": on_hand,
            "available_stock": on_hand - committed,
            "actual_available_stock": on_hand - committed,
            "reorder_level": reorder,
            "warehouses": warehouses,
            "created_time": "2025-11-02T10:15:00+0530",
        }

    people = rng.sample([(f, la) for f in FIRST for la in LAST], 20)
    for i, (first, last) in enumerate(people):
        cid = f"2300000000{i + 1:05d}"
        city, state, zip_code = rng.choice(CITIES)
        addr = _address(rng, city, state, zip_code)
        ds.contacts[cid] = {
            "contact_id": cid,
            "contact_name": f"{first} {last}",
            "company_name": "",
            "contact_type": "customer",
            "status": "active",
            "email": f"{first.lower()}.{last.lower()}@example.in",
            "phone": f"+91 9{rng.randint(100000000, 999999999)}",
            "outstanding_receivable_amount": rng.choice([0, 0, 0, 349, 1199, 2450]),
            "currency_code": "INR",
            "billing_address": addr,
            "shipping_address": addr,
            "gst_no": "",
            "created_time": f"2026-0{rng.randint(1, 6)}-1{rng.randint(0, 9)}T12:00:00+0530",
        }
    for j, (company, city, state, gst_state) in enumerate(BUSINESSES):
        cid = f"2300000001{j + 1:05d}"
        addr = _address(rng, city, state, "400001")
        ds.contacts[cid] = {
            "contact_id": cid,
            "contact_name": company,
            "company_name": company,
            "contact_type": "customer",
            "status": "active",
            "email": f"purchase@{company.split()[0].lower()}.example.in",
            "phone": f"+91 80{rng.randint(10000000, 99999999)}",
            "outstanding_receivable_amount": rng.choice([0, 15400, 48250]),
            "currency_code": "INR",
            "billing_address": addr,
            "shipping_address": addr,
            "gst_no": f"{gst_state}AAB{rng.randint(1000, 9999)}C1Z{rng.randint(1, 9)}",
            "created_time": "2025-12-01T09:30:00+0530",
        }
    ds.contacts["2300000009999"] = {
        "contact_id": "2300000009999",
        "contact_name": "Leaf & Co Wholesale",
        "company_name": "Leaf & Co",
        "contact_type": "vendor",
        "status": "active",
        "email": "sales@leafco.example.in",
        "phone": "+91 33 4000 1234",
        "outstanding_receivable_amount": 0,
        "currency_code": "INR",
        "billing_address": {},
        "shipping_address": {},
        "gst_no": "19AAAPL1234C1Z5",
        "created_time": "2025-10-01T09:30:00+0530",
    }

    active_items = [i for i in ds.items.values() if i["status"] == "active"]
    customers = [c for c in ds.contacts.values() if c["contact_type"] == "customer"]
    statuses = ["confirmed"] * 5 + ["closed"] * 8 + ["draft"] * 2 + ["void"] + ["onhold"]
    for n in range(1, 91):
        so_id = f"2500000000{n:05d}"
        customer = rng.choice(customers)
        date = AS_OF - dt.timedelta(days=int((90 - n) * 1.0) + rng.randint(0, 1))
        status = rng.choice(statuses)
        lines = []
        for li_n, item in enumerate(rng.sample(active_items, rng.randint(1, 4)), start=1):
            qty = rng.randint(25, 60) if item["sku"] == "GFT-CORP-25" else rng.randint(1, 6)
            shipped = qty if status == "closed" else (rng.randint(0, qty) if status == "confirmed" else 0)
            lines.append(
                {
                    "line_item_id": f"{so_id}{li_n}",
                    "item_id": item["item_id"],
                    "name": item["name"],
                    "sku": item["sku"],
                    "quantity": qty,
                    "rate": item["rate"],
                    "item_total": qty * item["rate"],
                    "unit": item["unit"],
                    "quantity_shipped": shipped,
                }
            )
        sub_total = sum(li["item_total"] for li in lines)
        shipping = 0 if sub_total >= 999 else 79
        tax = round(sub_total * 0.05, 2)
        all_shipped = all(li["quantity_shipped"] == li["quantity"] for li in lines)
        any_shipped = any(li["quantity_shipped"] for li in lines)
        ds.salesorders[so_id] = {
            "salesorder_id": so_id,
            "salesorder_number": f"SO-{n:05d}",
            "date": date.isoformat(),
            "shipment_date": (date + dt.timedelta(days=2)).isoformat(),
            "reference_number": f"WEB-{100200 + n}" if rng.random() < 0.7 else "",
            "customer_id": customer["contact_id"],
            "customer_name": customer["contact_name"],
            "status": status,
            "invoiced_status": "invoiced"
            if status == "closed"
            else ("not_invoiced" if status != "confirmed" else "partially_invoiced"),
            "paid_status": "paid" if status == "closed" else "unpaid",
            "shipped_status": (
                "shipped" if all_shipped else "partially_shipped" if any_shipped else "pending"
            )
            if status in ("closed", "confirmed")
            else "",
            "sub_total": sub_total,
            "tax_total": tax,
            "shipping_charge": shipping,
            "total": round(sub_total + tax + shipping, 2),
            "currency_code": "INR",
            "delivery_method": rng.choice(["Delhivery", "Blue Dart", "Shiprocket", "Self Pickup"]),
            "salesperson_name": rng.choice(["Online Store", "Rahul (B2B)", "Online Store"]),
            "line_items": lines,
            "shipping_address": customer["shipping_address"],
            "billing_address": customer["billing_address"],
            "notes": "Gift wrap requested." if rng.random() < 0.15 else "",
            "created_time": f"{date.isoformat()}T11:{rng.randint(10, 59)}:00+0530",
        }
    return ds
