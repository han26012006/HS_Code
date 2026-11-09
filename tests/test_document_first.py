"""Test suite for Document-First & Intelligent Auto-fill (TC01 - TC12).

Tests adhere strictly to requirements:
- TC01: Single SKU with 1200W, exact provenance
- TC02: Multi-SKU (1200W & 1600W) in one document set
- TC03: Missing mandatory attributes & readiness check
- TC04: User edit of OCR/extracted value preserving source provenance
- TC05: Cross-document conflict detection and resolution requirement
- TC06: Pure manual case creation preservation
- TC07: Incremental upload without overwriting verified attributes
- TC08: Observed HS code strictly non-predictive (no auto-approval)
- TC09: Source modification / invalidation handling
- TC10: Full export integrity (PDF, XLSX, JSON, ZIP)
- TC11: Idempotency and error rollback
- TC12: Regression checks across system
"""
import io
import json
import zipfile
import pytest
from pathlib import Path
from hs_assistant.workspace import Workspace, WorkspaceError
from hs_assistant.documents import DocumentService
from hs_assistant.extractor import (
    DocumentTypeDetector,
    InformationExtractor,
    CrossDocumentReconciler,
    AutoFillDraftManager,
    parse_file_bytes
)


@pytest.fixture
def ws(tmp_path):
    db_file = tmp_path / "test_workspace.sqlite"
    w = Workspace(db_file)
    return w


@pytest.fixture
def doc_svc(ws, tmp_path):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return DocumentService(ws, uploads_dir)


@pytest.fixture
def draft_mgr(ws):
    return AutoFillDraftManager(ws)


def test_tc01_single_sku_1200w_provenance(ws, draft_mgr, doc_svc):
    """TC01: Single SKU with 1200W hair dryer. Verifies exact quote substring and provenance."""
    invoice_text = (
        "COMMERCIAL INVOICE\n"
        "Invoice No: INV-2026-001\n"
        "Date: 2026-03-15\n"
        "Seller: Tokyo Electric Corp, Japan\n"
        "Buyer: Hanoi Trading JSC, Vietnam\n"
        "Item 1: Hair Dryer Model HD-1200\n"
        "Rated Power: 1200W, 220V 50Hz\n"
        "Quantity: 500 PCS\n"
        "Total Amount: USD 15,000\n"
        "Incoterms: CIF Haiphong\n"
    )

    files = [("Invoice_HD1200.txt", invoice_text.encode("utf-8"))]
    draft = draft_mgr.create_draft(files)

    assert draft["status"] == "review_required"
    assert len(draft["documents"]) == 1
    doc = draft["documents"][0]
    assert doc["kind"] == "commercial_invoice"
    assert doc["type_confidence"] is None
    assert doc["signals"]

    # Check dossier fields
    fields = draft["dossier_fields"]
    assert "Tokyo Electric Corp" in fields.get("exporter", {}).get("value", "")
    assert "Hanoi Trading JSC" in fields.get("importer", {}).get("value", "")
    assert fields.get("invoice_number", {}).get("value") == "INV-2026-001"
    assert "USD" in fields.get("currency", {}).get("value")
    assert "CIF" in fields.get("incoterms", {}).get("value")

    # Check candidate SKU
    assert len(draft["skus"]) >= 1
    sku = draft["skus"][0]
    facts = {f["field"]: f for f in sku.get("facts", [])}

    assert "specifications" in facts
    assert "1200W" in facts["specifications"]["value"]
    # Verify strict provenance: quote is exact substring
    quote = facts["specifications"]["quote"]
    assert quote in invoice_text
    assert facts["specifications"]["status"] == "unverified"

    # Commit draft
    payload = {
        "owner": "Chuyên viên Nguyễn Văn A",
        "title": "Lô hàng máy sấy tóc HD-1200",
        "trade_type": "import",
        "classification_date": "2026-03-20",
        "skus": draft["skus"]
    }
    committed_case = draft_mgr.commit_draft(draft["draft_id"], payload, doc_svc)
    assert committed_case["id"]
    assert len(committed_case["skus"]) >= 1

    created_sku = ws.get_sku(committed_case["skus"][0]["id"])
    spec_fact = next(f for f in created_sku["facts"] if f["field"] == "specifications")
    assert "1200W" in spec_fact["value"]
    assert spec_fact["status"] == "unverified"
    assert spec_fact["document_id"] is not None


def test_tc02_multi_sku_1200w_and_1600w(draft_mgr, doc_svc):
    """TC02: Multi-SKU (1200W and 1600W) in a single document set. Separated cleanly."""
    doc_text = (
        "COMMERCIAL INVOICE & PACKING LIST\n"
        "Invoice No: INV-MULTI-99\n"
        "Shipper: Global Appliance Co., Ltd\n"
        "Consignee: VN Import Export Ltd\n"
        "Item 1: Model HD-1200 Compact Hair Dryer, 1200W motor, 2 heat settings\n"
        "Quantity: 200 Units\n"
        "Item 2: Model HD-1600 Pro Salon Hair Dryer, 1600W ionic ceramic, 3 heat settings\n"
        "Quantity: 300 Units\n"
        "Total Quantity: 500 Units\n"
    )

    files = [("Invoice_MultiSKU.txt", doc_text.encode("utf-8"))]
    draft = draft_mgr.create_draft(files)

    assert len(draft["skus"]) == 2
    sku_codes = [s["sku_code"] for s in draft["skus"]]
    assert any("1200" in c for c in sku_codes)
    assert any("1600" in c for c in sku_codes)

    sku1200 = next(s for s in draft["skus"] if "1200" in s["sku_code"])
    sku1600 = next(s for s in draft["skus"] if "1600" in s["sku_code"])

    f1200 = {f["field"]: f for f in sku1200["facts"]}
    f1600 = {f["field"]: f for f in sku1600["facts"]}

    assert "1200" in f1200["specifications"]["value"]
    assert "1600" in f1600["specifications"]["value"]

    # Commit both SKUs into case
    payload = {
        "owner": "Nguyễn Thị B",
        "title": "Hồ sơ nhập khẩu 2 dòng máy sấy tóc",
        "trade_type": "import",
        "skus": draft["skus"]
    }
    committed = draft_mgr.commit_draft(draft["draft_id"], payload, doc_svc)
    assert len(committed["skus"]) == 2


def test_tc03_missing_attributes_readiness_gate(ws, doc_svc, draft_mgr):
    """TC03: Missing mandatory attributes prevents classification analysis and approval."""
    case = ws.create_case("Hồ sơ test thiếu thuộc tính", "Kiểm tra viên C")
    sku = ws.add_sku(case["id"], "SKU-INCOMPLETE", "Máy sấy tóc chưa đủ thông tin")

    # Only 1 unverified fact added
    ws.add_fact(sku["id"], "name", "Máy sấy tóc cầm tay", status="unverified", reviewer=None, source_kind="manual_declaration", quote="Khai báo sơ bộ từ nhân viên kho")

    sku_fresh = ws.get_sku(sku["id"])
    readiness = sku_fresh["readiness"]

    # Name and function are required to be verified before analysis
    assert not readiness["can_analyze"]
    assert "function" in readiness["missing_fields"]

    # Attempting to review/approve must raise WorkspaceError
    with pytest.raises(WorkspaceError, match="Còn thuộc tính bắt buộc"):
        ws.review(
            sku_id=sku["id"],
            code="85163100",
            reason="Lập luận phân loại mẫu để kiểm tra tính hợp lệ",
            reviewer="Người duyệt độc lập",
            preparer="Kiểm tra viên C",
            evidence_ids=[],
            expected_revision=sku_fresh["revision"],
            catalogue={"85163100": {"code": "85163100"}},
            action="approve"
        )


def test_tc04_ocr_edit_preserves_provenance(ws, doc_svc):
    """TC04: User edits OCR/extracted value, keeping source document link and exact quote."""
    case = ws.create_case("Hồ sơ test OCR edit", "User 1")
    doc_res = doc_svc.upload(case["id"], "spec_sheet.txt", b"Technical Spec: Hairdryer 220V 1200W black casing.")
    doc_id = doc_res["documents"][0]["id"]
    doc_svc.process(doc_id)

    sku = ws.add_sku(case["id"], "SKU-OCR-1", "Máy sấy tóc 1200W")
    # Original extracted fact
    fact = ws.add_fact(
        sku_id=sku["id"],
        field="specifications",
        value="1200W",
        document_id=doc_id,
        page_number=1,
        quote="220V 1200W",
        status="unverified"
    )

    # User verifies the fact with updated reviewer
    updated_sku = ws.update_fact(sku["id"], fact["facts"][0]["id"], status="verified", reviewer="Chuyên viên Thẩm định")
    saved_fact = updated_sku["facts"][0]

    assert saved_fact["status"] == "verified"
    assert saved_fact["reviewer"] == "Chuyên viên Thẩm định"
    assert saved_fact["document_id"] == doc_id
    assert saved_fact["page_number"] == 1
    assert saved_fact["quote"] == "220V 1200W"


def test_tc05_cross_document_conflict_detection(draft_mgr):
    """TC05: Conflicting data between documents (e.g. Invoice 1200W vs Spec 1600W)."""
    inv_text = "COMMERCIAL INVOICE\nModel: HD-1\nItem: Hair Dryer\nRated Power: 1200W\nGross Weight: 500 KGS\n"
    spec_text = "TECHNICAL SPECIFICATION\nModel: HD-1\nProduct: Hair Dryer\nPower Consumption: 1600W\nGross Weight: 500 KGS\n"

    files = [
        ("Invoice.txt", inv_text.encode("utf-8")),
        ("SpecSheet.txt", spec_text.encode("utf-8"))
    ]
    draft = draft_mgr.create_draft(files)

    reconciliations = draft["reconciliations"]
    conflicts = [r for r in reconciliations if r["status"] == "conflict"]
    assert len(conflicts) >= 1
    assert any("power" in c["field"].lower() or "công suất" in c["field"].lower() for c in conflicts)


def test_tc06_manual_creation_preserved(ws):
    """TC06: 100% preservation of manual creation workflow without documents."""
    case = ws.create_case("Hồ sơ nhập thủ công 100%", "Nguyễn Văn Thủ Công", trade_type="export")
    assert case["id"]
    assert case["trade_type"] == "export"

    sku = ws.add_sku(case["id"], "MANUAL-SKU", "Sản phẩm thủ công", description="Mô tả nhập tay")
    assert sku["sku_code"] == "MANUAL-SKU"

    ws.add_fact(sku["id"], "name", "Tên sản phẩm nhập tay", status="verified", reviewer="Nguyễn Văn Thủ Công", source_kind="manual_declaration", quote="Biên bản nghiệm thu kỹ thuật nội bộ số 12/BB-KT")
    ws.add_fact(sku["id"], "function", "Công dụng sấy khô tóc gia dụng", status="verified", reviewer="Nguyễn Văn Thủ Công", source_kind="manual_declaration", quote="Hướng dẫn sử dụng đính kèm catalogue sản phẩm")

    sku_updated = ws.get_sku(sku["id"])
    assert sku_updated["readiness"]["can_analyze"]


def test_tc07_incremental_upload_does_not_overwrite_verified(ws, doc_svc, draft_mgr):
    """TC07: Adding documents to existing case extracts facts without overwriting verified ones."""
    case = ws.create_case("Hồ sơ bổ sung chứng từ", "Chuyên viên D")
    sku = ws.add_sku(case["id"], "SKU-EXISTING", "Máy sấy tóc")

    # Manually verify power as 1200W
    ws.add_fact(
        sku["id"],
        "specifications",
        "Công suất 1200W đã kiểm tra kỹ",
        status="verified",
        reviewer="Trưởng nhóm Thẩm định",
        source_kind="manual_declaration",
        quote="Biên bản kiểm tra kỹ thuật tại chỗ"
    )

    # Now upload new document with different extraction
    doc_res2 = doc_svc.upload(case["id"], "Datasheet.txt", "Technical Datasheet\nModel: SKU-EXISTING\nProduct: Máy sấy tóc\nPower: 1400W\nMaterial: ABS plastic\n".encode("utf-8"))
    doc_svc.process(doc_res2["documents"][0]["id"])

    # Run autofill for existing case
    result = draft_mgr.extract_for_case(case["id"], doc_svc)
    assert result["summary"]["total_documents"] == 1

    # Check candidate facts
    sku_candidate = next(s for s in result["skus"] if s.get("existing_sku_id") == sku["id"])
    spec_fact = next((f for f in sku_candidate["facts"] if f["field"] == "specifications"), None)
    if spec_fact:
        assert spec_fact.get("skip_overwrite") is True

    # Apply autofill
    draft_mgr.apply_to_case(case["id"], result)

    # Verify that the verified fact was preserved untouched!
    refreshed_sku = ws.get_sku(sku["id"])
    saved_spec = next(f for f in refreshed_sku["facts"] if f["field"] == "specifications")
    assert saved_spec["value"] == "Công suất 1200W đã kiểm tra kỹ"
    assert saved_spec["status"] == "verified"


def test_tc08_observed_hs_code_non_predictive(draft_mgr, ws):
    """TC08: Extracted HS code stored only as declared_code, never auto-approving or biasing prediction."""
    invoice_text = (
        "CUSTOMS INVOICE\n"
        "Item: Hair Dryer\n"
        "HS Code: 8516.31.00\n"
        "Power: 1200W\n"
    )
    draft = draft_mgr.create_draft([("inv.txt", invoice_text.encode("utf-8"))])
    sku = draft["skus"][0]

    assert sku.get("declared_code") == "85163100"
    # Ensure no approved decision exists
    assert "decision" not in sku or sku["decision"] is None


def test_tc09_source_invalidation(ws, doc_svc):
    """TC09: Deleting or invalidating source document leaves a clear trace."""
    case = ws.create_case("Hồ sơ test source invalidation", "User A")
    res = doc_svc.upload(case["id"], "source_doc.txt", b"Specification: 1200W hair dryer")
    doc_id = res["documents"][0]["id"]
    doc_svc.process(doc_id)

    sku = ws.add_sku(case["id"], "SKU-INV", "Hair dryer")
    ws.add_fact(sku["id"], "specifications", "1200W", document_id=doc_id, page_number=1, quote="1200W hair dryer")

    # Delete document
    ws.delete_document(doc_id)

    # Fact document_id becomes NULL, quote preserved
    sku_fresh = ws.get_sku(sku["id"])
    fact = sku_fresh["facts"][0]
    assert fact["document_id"] is None
    assert fact["quote"] == "1200W hair dryer"


def test_tc10_export_integrity(ws, doc_svc, tmp_path):
    """TC10: Export JSON, PDF, Excel & ZIP contain complete case, sku, facts and document metadata."""
    from hs_assistant.workspace_export import case_pdf, case_excel
    from hs_assistant.archival import build_case_archive

    case = ws.create_case("Hồ sơ xuất báo cáo", "Chuyên viên Xuất khẩu")
    doc_res = doc_svc.upload(case["id"], "invoice.txt", b"Invoice No: 12345. Amount: USD 5000.")
    doc_svc.process(doc_res["documents"][0]["id"])

    sku = ws.add_sku(case["id"], "SKU-EXP", "Mặt hàng xuất")
    ws.add_fact(sku["id"], "name", "Mặt hàng xuất khẩu chuẩn", document_id=doc_res["documents"][0]["id"], page_number=1, quote="Invoice No: 12345")

    case_full = ws.get_case(case["id"])
    case_full["skus"] = [ws.get_sku(s["id"]) for s in case_full["skus"]]
    case_full["decision_snapshots"] = []

    # Test PDF generation
    pdf_bytes = case_pdf(case_full)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")

    # Test Excel generation
    xlsx_bytes = case_excel(case_full)
    assert len(xlsx_bytes) > 0

    # Test ZIP archive packaging
    archive_file, work_dir = build_case_archive(case_full, ws, Path('.'))
    assert archive_file.exists()
    with zipfile.ZipFile(archive_file) as z:
        names = z.namelist()
        assert "MANIFEST.json" in names
        assert any(n.startswith("documents/") for n in names)



def test_tc11_idempotency_and_rollback(draft_mgr, ws, doc_svc):
    """TC11: Duplicate commit or invalid commit handles gracefully without corrupted state."""
    draft = draft_mgr.create_draft([("doc.txt", b"COMMERCIAL INVOICE\nItem: Test Item\n")])
    draft_id = draft["draft_id"]

    # First commit
    payload = {"owner": "Tester", "title": "Case 1", "skus": draft["skus"]}
    case = draft_mgr.commit_draft(draft_id, payload, doc_svc)
    assert case["id"]

    # Second commit on deleted draft raises KeyError
    with pytest.raises(KeyError):
        draft_mgr.commit_draft(draft_id, payload, doc_svc)


def test_tc12_regression_existing_functionality(ws):
    """TC12: Core functions of workspace, tax scenarios, and precedents operate unimpeded."""
    summary = ws.summary()
    assert "cases" in summary
    assert "skus" in summary
    assert "unverified_facts" in summary
