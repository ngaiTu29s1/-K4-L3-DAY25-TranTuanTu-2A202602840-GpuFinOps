---
# Metadata của Lab. Điền giá trị bên phải dấu ":".
title: "GPU FinOps — Tối ưu hóa Chi phí GPU" # Tên Codelab
description: "Đóng vai FinOps Engineer tại NimbusAI: phân tích telemetry GPU, giá GPU và log token để cắt giảm 40–95% chi phí, đo bằng $/1M-token." # Tóm tắt ngắn cho học viên
author: "VinUni Codelab" # Tác giả
duration: 240 # 4 tiếng (240 phút)
category: "Infrastructure & FinOps" # Nhóm nội dung
updated: "2026-10-14" # Tự điền ngày hiện tại (YYYY-MM-DD)
day: "25" # Day của cohort
sequence: 1 # Thứ tự hiển thị trong cùng Day (số nhỏ hơn hiện trước)
keywords: ["GPU", "FinOps", "Cost Optimization", "LLM Inference", "MFU", "FOCUS", "Sustainability"] # Ví dụ: ["AI", "API"]
level: "intermediate" # beginner hoặc intermediate
requiresSubmission: true # true nếu học viên cần nộp bài
workMode: "individual" # Bắt buộc: individual hoặc team
overview: # Tùy chọn; điền đủ các phần dưới để hiện Bản đồ Lab
  summary: "Lab thuần Python (không cần GPU/cloud/API key) mô phỏng một startup LLM có hóa đơn GPU mất kiểm soát. Qua 5 mission, học viên kiểm toán hiệu quả GPU, áp dụng các đòn bẩy giảm chi phí inference, chọn chiến lược mua GPU, phân bổ chi phí theo team và tổng hợp báo cáo baseline vs. optimized."
  knowledge:
    - "MFU (Model FLOPs Utilization) và MBU (Model Bandwidth Utilization) khác GPU-Util % như thế nào"
    - "Roofline model: phân biệt workload compute-bound và memory-bound"
    - "Các đòn bẩy giảm $/1M-token: cascade routing, prompt caching, batch API"
    - "So sánh on-demand / spot / reserved và điểm hòa vốn (break-even utilization)"
    - "Thang trưởng thành phân bổ chi phí: Visibility → Showback → Chargeback, và chuẩn FOCUS"
    - "Liên hệ giữa chi phí điện, carbon và vùng triển khai (sustainability)"
  conceptFlow:
    - "Đọc dữ liệu telemetry/giá/token → phát hiện GPU-Util lie và lãng phí idle (M1)"
    - "Tính chi phí request và áp dụng cascade + cache + batch để giảm $/1M-token (M2)"
    - "Chọn tier mua GPU theo duty cycle và khả năng gián đoạn (M3)"
    - "Gắn tag và phân bổ chi phí theo team, xuất dữ liệu chuẩn FOCUS (M4)"
    - "Tổng hợp baseline vs. optimized thành báo cáo kèm biểu đồ waterfall và phần sustainability (M5)"
  phases:
    - time: "30 phút"
      owner: "Học viên"
      title: "Cài đặt & khám phá dữ liệu"
      description: "Tạo virtual environment, cài thư viện, chạy verify.py và data/generate.py, đọc qua 4 file CSV đầu vào."
    - time: "120 phút"
      owner: "Học viên"
      title: "Chạy 5 Mission (M1–M5)"
      description: "Đọc code trong finops/, chạy từng mission, trả lời câu hỏi phân tích kết quả sau mỗi mission."
    - time: "60 phút"
      owner: "Học viên"
      title: "Phần mở rộng Your Turn"
      description: "Chọn và triển khai ≥2 trong 5 extension (tier policy, right-sizing MBU, cache_is_worth_it, ngân sách reasoning, carbon-aware scheduling)."
    - time: "30 phút"
      owner: "Học viên"
      title: "Kiểm tra & chuẩn bị nộp bài"
      description: "Chạy verify.py (11/11) và pytest (15 passed), viết write-up ngắn, đóng gói outputs/ để nộp."
  outcomes:
    - "Chạy được toàn bộ pipeline FinOps thuần Python và đạt verify.py 11/11 + pytest 15/15"
    - "Giải thích được vì sao GPU-Util cao không đồng nghĩa hiệu quả tính toán cao (MFU thấp)"
    - "Tạo được báo cáo baseline vs. optimized theo $/1M-token với breakdown từng đòn bẩy tiết kiệm"
    - "Triển khai và đo lường được ít nhất 2 phần mở rộng nâng cao"
  reassurance: "Lab chạy hoàn toàn trên laptop, không cần GPU thật, không cần tài khoản cloud hay API key — mọi dữ liệu đều được sinh tất định (seed=25) nên kết quả luôn tái lập được."
---

## 1. Thuật ngữ cần biết

| Thuật ngữ gốc | Bản chất khái niệm | Minh hoạ trực quan |
| --- | --- | --- |
| `MFU` (Model FLOPs Utilization) | % FLOPs thực sự dùng so với FLOPs đỉnh (peak) của GPU — đo hiệu quả tính toán thật, không phải "GPU có đang bận hay không" | `gpu-h100-4` có `GPU-Util = 98%` nhưng `MFU ≈ 0.20` — bạn trả tiền cho cả giờ H100 nhưng chỉ nhận 1/5 FLOPs |
| `MBU` (Model Bandwidth Utilization) | % băng thông bộ nhớ HBM thực dùng / peak — chỉ số quan trọng cho workload memory-bound như decode | Một job decode LLM có MBU thấp nghĩa là GPU đang "chờ dữ liệu" nhiều hơn là tính toán |
| `GPU-Util lie` | `nvidia-smi` chỉ đo "clock đang bận", không đo FLOPs thực sự sinh ra — dễ đánh lừa người mua sắm hạ tầng | Nhiệm vụ M1 phải phát hiện đúng GPU nào đang "nói dối" trong 11 GPU của telemetry |
| `$/1M-token` | Đơn vị chi phí chuẩn hoá theo sản lượng token, thay vì theo giờ thuê GPU | Hai team trả cùng `$/GPU-giờ` nhưng team tối ưu tốt hơn phục vụ được 10× số token |
| `Cascade routing` | Định tuyến request sang model nhỏ, rẻ hơn (thường ~15×), chỉ dùng model lớn khi thực sự cần | M2 mô phỏng chuyển bớt traffic từ `route_tier="large"` sang `"small"` |
| `Prompt Caching` | Phần input trùng lặp đã được cache chỉ tính 10% giá gốc (chiết khấu 90%) | Trong `token_usage.csv`, cột `cached_input_tokens` là phần được hưởng mức giá này |
| `Batch API` | Gộp các request không cần phản hồi real-time để hưởng chiết khấu 50% | Cột `is_batch=1` trong dữ liệu token đánh dấu các request đủ điều kiện |
| `Break-even utilization` | Mức sử dụng tối thiểu để reserved instance có lợi hơn on-demand: `1 - discount` | Với chiết khấu reserved 45% → cần duty cycle ≥ 55% (~13.2 giờ/ngày) mới nên mua reserved |
| `Showback / Chargeback` | Showback = hiển thị chi phí theo team để nhận thức; Chargeback = thực sự thu tiền, chỉ làm được khi tag coverage ≥ 80% | M4 kiểm tra `tag_coverage` trước khi bật "chargeback ready" |
| `FOCUS` | Chuẩn dữ liệu chi phí cloud mở, đa nhà cung cấp (FinOps Foundation) | M4 xuất `outputs/focus_export.csv` theo đúng schema FOCUS (`BilledCost`, `ServiceCategory`, ...) |
| `Roofline model` | Mô hình xác định workload bị giới hạn bởi compute hay bởi bandwidth, dựa trên arithmetic intensity so với ridge point của GPU | LLM prefill (~455 FLOP/byte) là compute-bound; LLM decode (~1–2 FLOP/byte) là memory-bound trên H100 |

## 2. Mục tiêu & đầu ra

Bạn hoàn thành khi:

- `python verify.py` báo **11/11 checks passed**.
- `pytest -q` báo **15 passed**.
- Thư mục `outputs/` có đủ `report.md`, `savings.png`, `focus_export.csv`, thể hiện rõ chi phí baseline vs. optimized theo `$/1M-token` với breakdown từng đòn bẩy.
- Bạn đã triển khai và đo lường được **ít nhất 2 trong 5** phần mở rộng "Your Turn" (xem mục 4.3).
- Bạn nộp kèm một bài viết ngắn (1–2 trang) phân tích kết quả theo yêu cầu ở mục 6.

## 3. Chuẩn bị

- Python 3.9+ đã cài trên máy (không cần GPU thật, không cần tài khoản cloud, không cần API key).
- Repo bài lab: [VinUni-AI20k/Day25-Track2-GpuFinOps](https://github.com/VinUni-AI20k/Day25-Track2-GpuFinOps) — clone hoặc mở thư mục `Day25-Track2-GPU-FinOps-Lab` đã có sẵn.
- Đã đọc qua slide `day25-gpu-finops-cost-optimization` để nắm bối cảnh trước khi vào lab.
- Thư viện Python cần thiết (cài qua `requirements.txt`): `pandas>=2.0`, `matplotlib>=3.7`, `pytest>=7.4`.

```bash
cd Day25-Track2-GPU-FinOps-Lab
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python verify.py                 # phải in ra 11/11 checks passed (baseline trước khi bạn sửa gì)
```

## 4. Thực hành

### 4.1 Khám phá dữ liệu đầu vào

```bash
python data/generate.py   # sinh 4 file CSV trong data/, seed cố định = 25
```

Đọc nhanh 4 file: `price_catalog.csv` (giá 7 loại GPU), `gpu_telemetry.csv` (11 GPU × 24 giờ), `token_usage.csv` (2,400 request LLM), `workloads.csv` (8 job training/inference). Chi tiết cột và ví dụ code đọc từng file có trong [Guide.md](Guide.md#3-khám-phá-dữ-liệu-đầu-vào).

**Kết quả mong đợi:** 4 file `.csv` xuất hiện trong `data/`, đọc bằng `pandas.read_csv` không lỗi.

### 4.2 Chạy 5 Mission

| # | Lệnh chạy | Bạn học được gì | Kết quả mong đợi |
| --- | --- | --- | --- |
| M1 | `python missions/m1_efficiency_audit.py` | Kiểm toán hiệu quả — MFU/MBU, "GPU-Util lie", lãng phí idle | In ra bảng GPU kèm util/MFU/MBU, liệt kê `gpu-h100-4` là GPU-Util lie, tính idle waste ($/tháng) |
| M2 | `python missions/m2_inference_levers.py` | Đòn bẩy chi phí inference — `$/1M-token`, cascade × cache × batch | `baseline` vs `optimized` theo `$/1M-token`, savings trong khoảng 60–95% |
| M3 | `python missions/m3_purchasing.py` | Chiến lược mua GPU — điểm hòa vốn, spot/reserved, checkpoint simulation | Mỗi job được gán tier (`spot`/`reserved`/`on_demand`), tổng savings > 0 |
| M4 | `python missions/m4_allocation.py` | Phân bổ chi phí theo tag → showback → chargeback, FOCUS export | Chi phí theo team, tag coverage 85–100%, file `outputs/focus_export.csv` |
| M5 | `python missions/m5_report.py` | Báo cáo tối ưu — gộp M1–M4 thành baseline vs. optimized + sustainability | `outputs/report.md` + `outputs/savings.png`, tổng savings trong khoảng 40–95% |

Sau mỗi mission, dừng lại trả lời các câu hỏi phân tích tương ứng trong [Guide.md](Guide.md) (mục 4.3, 5.4, 6.4, 7.4) — đây là phần giúp bạn hiểu bản chất thay vì chỉ chạy script.

Có thể chạy nối tiếp cả 5 mission cùng lúc:

```bash
python missions/run_all.py
```

### 4.3 Phần mở rộng "Your Turn" (chọn ≥ 2/5)

Lab vẫn pass mà không cần làm phần này, nhưng đây là nơi học sâu nhất và chiếm 20% điểm rubric:

1. **Cải thiện `recommend_tier()`** (`finops/pricing.py`) — thêm interruption rate theo GPU type, so sánh 1yr vs 3yr reserved.
2. **Right-sizing theo MBU** (`missions/m1_efficiency_audit.py`) — dùng `$/GB-VRAM` và `peak_bw_tbs` để đề xuất GPU phù hợp hơn cho workload memory-bound.
3. **`cache_is_worth_it()`** (`finops/pricing.py` + `missions/m2_inference_levers.py`) — chỉ tính savings từ cache khi số lần đọc đủ bù chi phí ghi.
4. **Ngân sách Reasoning** (`missions/m2_inference_levers.py`, `missions/m5_report.py`) — tách chi phí `$`/`Wh` cho traffic `is_reasoning=1` và đề xuất quy tắc routing.
5. **Carbon-aware Scheduling** (`missions/m3_purchasing.py` hoặc file mới) — di chuyển job interruptible sang vùng rẻ + sạch nhất, báo cáo carbon tiết kiệm được.

Chi tiết yêu cầu và code mẫu cho từng extension nằm trong [Guide.md, mục 10](Guide.md#10-phần-mở-rộng-your-turn); tiêu chí chấm chi tiết nằm trong [Rubric.md, mục D](Rubric.md).

## 5. Kiểm tra kết quả

```bash
python verify.py   # phải đạt 11/11 checks passed
pytest -q          # phải đạt 15 passed
cat outputs/report.md
```

**Lỗi thường gặp** (xem đầy đủ tại [Guide.md, mục 12](Guide.md#12-các-lỗi-thường-gặp)):

- `ModuleNotFoundError: No module named 'pandas'` → virtual environment chưa được kích hoạt, kiểm tra `which python`.
- `FileNotFoundError: data/gpu_telemetry.csv` → chưa chạy `python data/generate.py`.
- `verify.py` fail ở "M2 savings out of band" → kiểm tra `request_cost()` trong `finops/pricing.py` có áp đúng `cache_discount=0.10` và `batch_discount=0.50`.
- `pytest` fail `test_flag_util_lies` → nhớ chia `gpu_util_pct` cho 100 trước khi so sánh ngưỡng `>= 0.90`.
- Không có `savings.png` → lab vẫn pass nếu thiếu matplotlib, nhưng nên `pip show matplotlib` để kiểm tra lại.

**Lưu ý:** không được sửa file trong `tests/` — nếu phát hiện test bị sửa để hardcode kết quả, toàn bộ điểm phần B (unit tests) sẽ bị trừ (xem [Rubric.md](Rubric.md)).

## 6. Nộp bài

Nộp các file sau (đúng theo [Rubric.md](Rubric.md)):

```
outputs/report.md
outputs/savings.png
outputs/focus_export.csv
[bài viết ngắn 1–2 trang — .md hoặc .pdf]
```

Bài viết ngắn cần trả lời:

1. **Baseline vs. Optimized:** chi phí trước/sau, `$/1M-token` trước/sau, tổng % tiết kiệm.
2. **Phân tích từng đòn bẩy:** đòn bẩy nào đóng góp nhiều nhất, tại sao.
3. **GPU-Util Lie:** GPU nào bị "lie", tác động tài chính là gì.
4. **Phần mở rộng đã làm:** mô tả từng extension, kết quả đo được, insight quan trọng nhất.
5. **Khuyến nghị cho NimbusAI:** 3 hành động đầu tiên nếu bạn là FinOps lead.

Checklist trước khi nộp:

```
[ ] python verify.py  →  11/11 checks passed
[ ] pytest -q         →  15 passed
[ ] outputs/report.md tồn tại và có đủ section (baseline/optimized, breakdown lever, sustainability)
[ ] outputs/savings.png tồn tại
[ ] outputs/focus_export.csv tồn tại
[ ] Đã thực hiện ≥2 extension với kết quả đo lường cụ thể
```

Bài lab được dùng làm **đầu vào cho Milestone 2** — mang báo cáo đến buổi demo platform. Repo gốc của bài lab: [VinUni-AI20k/Day25-Track2-GpuFinOps](https://github.com/VinUni-AI20k/Day25-Track2-GpuFinOps).
