# BÁO CÁO KỸ THUẬT & PHÂN TÍCH TỐI ƯU HÓA GPU FINOPS
**Dự án:** NimbusAI — GPU Cost & Efficiency Optimization  
**Khóa học:** AICB · Phase 2 · Track 2 (Infrastructure) · Day 25  
**Học viên:** Trần Tuấn Tú (Mã học viên: 2A202602840)  
**Ngày hoàn thành:** 2026-10-14  

---

## 1. Tổng quan Chi phí: Baseline vs. Optimized

### 1.1 Số liệu tài chính tổng hợp
Dưới sự bùng nổ của khối lượng truy vấn inference và nhu cầu huấn luyện mô hình nền tảng, chi phí vận hành hạ tầng GPU tại NimbusAI đã vượt ngoài tầm kiểm soát khi tính theo đơn vị truyền thống `$/GPU-giờ`. Bằng cách chuyển dịch trọng tâm sang đơn vị sản lượng chuẩn hóa **`$/1M-token`** kết hợp chiến lược mua sắm đa tầng (multi-tier purchasing), chúng tôi đã tái cấu trúc toàn diện bảng cân đối chi phí:

| Chỉ số đo lường | Baseline (Trước tối ưu) | Optimized (Sau tối ưu) | Mức độ cắt giảm |
|---|---|---|---|
| **Tổng chi phí hàng tháng (Total Spend)** | **$27,133 / tháng** | **$14,626 / tháng** | **-$12,507 (-46.1%)** |
| **Chi phí Inference theo ngày** | $48.87 / ngày | $8.48 / ngày | -$40.39 (-82.6%) |
| **Chi phí Inference quy đổi (Unit Cost)** | **$6.488 / 1M-token** | **$1.126 / 1M-token** | **-$5.362 (-82.6%)** |
| **Chi phí Mua sắm Hạ tầng (Purchasing)** | $25,667 / tháng | $15,627 / tháng | -$10,040 (-39.1%) |
| **Lãng phí do GPU Idle** | $600 / tháng | $0 / tháng | -$600 (-100%) |
| **Lãng phí do phần cứng "Util-Lie"** | $655 / tháng | $0 / tháng | -$655 (-100%) |

### 1.2 Ý nghĩa của chỉ số `$/1M-token`
Trong mô hình kinh tế AI hiện đại, đơn vị `$/GPU-giờ` chỉ phản ánh *số tiền doanh nghiệp phải trả cho một đơn vị thời gian thuê máy*, nhưng hoàn toàn không đo lường được *sản lượng và giá trị nghiệp vụ tạo ra*. Hai đội ngũ kỹ thuật có thể cùng chi trả $2.50/giờ cho một GPU H100, nhưng đội ngũ triển khai pipeline tối ưu (batching, prompt caching, model cascading) có thể phục vụ số lượng token gấp 10× so với đội ngũ chạy naive inference. Đơn vị chuẩn hóa `$/1M-token` buộc tổ chức phải quản trị đồng thời cả **hiệu quả sử dụng phần cứng** lẫn **kiến trúc phần mềm AI**.

---

## 2. Phân tích Chi tiết Từng Đòn Bẩy Tiết Kiệm (Savings Levers)

Biểu đồ Waterfall (được xuất tại `outputs/savings.png`) ghi nhận 4 đòn bẩy đóng góp vào tổng khoản tiết kiệm **$12,507 / tháng**:

```
[Baseline: $27,133]
   │
   ├─► Purchasing Strategy (Spot / Reserved) : -$10,040  (80.3% tổng savings)
   ├─► Inference Levers (Cascade / Cache / Batch): -$1,212   (9.7% tổng savings)
   ├─► Right-sizing "Util-Lie" GPUs          : -$655     (5.2% tổng savings)
   └─► Elimination of Idle Waste             : -$600     (4.8% tổng savings)
   │
[Optimized: $14,626]
```

### 2.1 Đòn bẩy Purchasing Strategy (Spot & Reserved Instances) — Đóng góp lớn nhất: $10,040/tháng
- **Tại sao đóng góp lớn nhất?** Huấn luyện mô hình (Training) và tinh chỉnh (Fine-tuning) chiếm phần lớn ngân sách GPU thô. Trước khi tối ưu, toàn bộ 8 workload đều được chạy trên biểu giá On-demand đắt đỏ ($25,667/tháng).
- **Cơ chế triển khai:**
  - **Spot + Checkpointing:** Đối với các tác vụ có thể gián đoạn (`interruptible=1`) như `job-train-llm` (8× H100), `job-train-embed` (4× A100), `job-finetune` (2× H100), hệ thống chuyển sang thuê GPU Spot với mức chiết khấu 40–60%. Mô phỏng checkpointing (`ckpt_overhead_frac=3%`, `rework_hours=0.5h/gián đoạn`) chứng minh rằng ngay cả khi có gián đoạn mạng, chi phí Spot hiệu dụng vẫn tiết kiệm từ 35% đến 57% so với On-demand.
  - **Reserved Instances (Cam kết 3 năm):** Đối với các service inference phục vụ người dùng 24/7 (`duty_cycle=100%`) như `job-infer-chat` (A10G) và `job-infer-rag` (A100), mức sử dụng vượt xa điểm hòa vốn **Break-even Utilization = 55%** (`1 - 0.45`). Cam kết Reserved giúp cố định mức giảm 45% chi phí mà không mang rủi ro gián đoạn.

### 2.2 Đòn bẩy Inference Architecture (Cascade, Prompt Caching, Batch API): $1,212/tháng (giảm 82.6% chi phí inference)
- **Model Cascading:** 80% truy vấn của người dùng là các câu hỏi thường nhật/đơn giản, chỉ cần model nhỏ (`small`: $0.20 input / $0.40 output trên 1M tokens), thay vì chuyển toàn bộ vào model lớn (`large`: $3.00 input / $15.00 output). Chỉ 20% truy vấn phức tạp mới định tuyến đến model lớn.
- **Prompt Caching:** Trong RAG và Chatbot, system prompt và ngữ cảnh tài liệu lặp lại giữa các turn được cache và chỉ tính 10% giá input (giảm 90%). Trong 2,400 request kiểm toán, có 1,703,990 cached tokens (đạt tỷ lệ 31.9% tổng input tokens).
- **Batch API:** Gộp các request phi thời gian thực từ đội `eval` (chiếm 100% eval traffic) giúp nhận chiết khấu 50%.
- **Hiệu ứng chồng chiết khấu (Discount Stacking):** Với request được batch và cache 100%, chi phí chỉ còn `0.5 × 0.1 = 0.05` (tiết kiệm tới 95% so với mức giá ban đầu).

### 2.3 Đòn bẩy Right-sizing phần cứng "Util-Lie": $655/tháng
Hạ cấp các GPU bị nghẽn băng thông bộ nhớ hoặc lãng phí năng lực tính toán danh định xuống các phân khúc GPU tương thích nhưng chi phí rẻ hơn (H100 → A100; A100 → A10G; A10G → L4).

### 2.4 Đòn bẩy Diệt trừ Lãng phí Idle (Kill Idle Waste): $600/tháng
Phát hiện và tự động tắt instance `gpu-h100-5` bị bỏ trống 8 tiếng mỗi đêm ($20/ngày = $600/tháng).

---

## 3. Bản chất của "GPU-Util Lie" và Tác động Tài chính

### 3.1 Nhận diện thực tế
Trong đợt kiểm toán M1 trên 11 GPU thuộc hệ thống telemetry, hai GPU bị phát hiện "nói dối" nghiêm trọng:
1. **`gpu-h100-4` (H100):** `GPU-Util = 98.2%`, nhưng `MFU = 0.194` (19.4%) và `MBU = 0.207` (20.7%).
2. **`gpu-a10g-1` (A10G):** `GPU-Util = 96.9%`, nhưng `MFU = 0.268` (26.8%) và `MBU = 0.302` (30.2%).

### 3.2 Cơ chế kỹ thuật: Tại sao GPU-Util 98% nhưng MFU chỉ ~20%?
- **Chỉ số `nvidia-smi` đo gì?** Chỉ số `gpu_util_pct` trong driver NVIDIA chỉ đo **tỷ lệ thời gian mà một GPU engine (kernel) đang active** trong chu kỳ lấy mẫu. Chỉ cần 1 thread đang chạy hoặc GPU đang chờ bộ nhớ nhưng clock chưa hạ, chỉ số này đã nhảy lên 98–100%.
- **Chỉ số MFU (Model FLOPs Utilization) đo gì?** MFU đo tỷ lệ phần trăm giữa **số phép tính FLOPs thực tế sinh ra** so với năng lực tính toán cực đại (Peak Theoretical FLOPs) của chip. MFU lành mạnh của LLM training là 35–45%; >50% là xuất sắc.
- **Nguyên nhân gốc rễ:**
  1. **Memory-bound Stalls (Nghẽn băng thông bộ nhớ):** Theo mô hình **Roofline**, điểm bẻ cong (Ridge Point) của H100 BF16 là ~295 FLOP/byte. Trong giai đoạn LLM Decode hoặc unbatched inference, cường độ tính toán (Arithmetic Intensity) chỉ đạt ~1–2 FLOP/byte. Tensor Cores phải nhàn rỗi hàng nghìn chu kỳ clock để đợi nạp trọng số từ HBM vào SRAM.
  2. **Kernel Launch Overhead & CPU Host Synchronization:** Việc phóng các kernel quá nhỏ rời rạc mà không dùng CUDA Graphs khiến GPU liên tục bận rộn chuyển đổi ngữ cảnh nhưng không tính toán được bao nhiêu.
  3. **I/O Wait & Pipeline Bubbles:** GPU đang chờ batch dữ liệu nạp qua mạng/ổ đĩa.

### 3.3 Tác động tài chính
Doanh nghiệp đang trả tiền trọn gói cho phần cứng đắt tiền nhất thị trường ($2.50/giờ cho H100) nhưng chỉ thu lại năng lực tính toán tương đương một GPU phân khúc thấp hơn nhiều. Đây là hiện tượng "lỗ kép": vừa lãng phí vốn đầu tư, vừa làm suy giảm throughput trên mỗi watt điện tiêu thụ.

---

## 4. Chi tiết Các Phần Mở Rộng "Your Turn" Đã Triển Khai

Chúng tôi đã triển khai đầy đủ **cả 5 extensions**, tích hợp mã nguồn trực tiếp vào hệ thống engine và bổ sung test suite `tests/test_extensions.py` (tất cả 19 tests đều vượt qua).

### 4.1 Extension 1: Chính sách Mua sắm Nâng cao (`recommend_tier_advanced`)
- **Triển khai:** Tại `finops/pricing.py` và `missions/m3_purchasing.py`.
- **Cơ chế cải tiến:** 
  - Khác với quy tắc đơn giản ban đầu, hàm nâng cao cân nhắc ma trận 3 chiều: **(1) Tỷ lệ gián đoạn riêng biệt theo dòng GPU (`H100`: 3%, `A100`: 5%, `A10G`: 8%)**, **(2) Thời hạn thực tế của công việc (`job_days`)**, và **(3) Chi phí khóa vốn dài hạn (1yr vs 3yr commitment)**.
  - Đối với các job ngắn ngày (< 60 ngày), chính sách ngăn chặn việc cam kết Reserved 3 năm gây lãng phí công suất nhàn rỗi.
- **Kết quả đo lường:** Chi phí mua sắm theo chính sách nâng cao đạt **$15,551 / tháng** (tiết kiệm **39.4%**), cải thiện thêm so với chính sách cơ bản ($15,627 / tháng, 39.1%) nhờ mô hình hóa chính xác chi phí gián đoạn của H100 thấp hơn dự tính ban đầu.

### 4.2 Extension 2: Right-sizing Phần cứng theo MBU
- **Triển khai:** Tại `finops/metrics.py` và `missions/m1_efficiency_audit.py`.
- **Cơ chế cải tiến:** Xây dựng hàm `rightsize_mbu_candidates()`, phân tích chỉ số kinh tế đơn vị **`$/GB-VRAM-hr`** và **`$/(TB/s)-BW-hr`**. Với các workload memory-bound đạt băng thông thực tế thấp, hệ thống quét catalog để tìm GPU rẻ hơn nhưng vẫn đảm bảo mức băng thông tối thiểu (kèm 10% headroom).
- **Kết quả đo lường:**
  - `gpu-h100-4` (đạt 0.692 TB/s trên H100 giá $2.50) được đề xuất chuyển sang `A100` (băng thông 2.0 TB/s, giá $1.79) → tiết kiệm **$511/tháng**.
  - `gpu-a100-1` (đạt 0.495 TB/s trên A100 giá $1.79) chuyển sang `A10G` (0.60 TB/s, giá $1.00) → tiết kiệm **$569/tháng**.
  - Tổng tiềm năng tiết kiệm khi right-size theo MBU đạt **$1,879 / tháng**.

### 4.3 Extension 3: Kinh tế học của Prompt Caching (`cache_is_worth_it`)
- **Triển khai:** Tại `finops/pricing.py` và `missions/m2_inference_levers.py`.
- **Cơ chế cải tiến:** Prompt caching trong thực tế không miễn phí; nhà cung cấp tính phí tạo cache (Cache Write Overhead ~ 1.25× giá input cơ sở) hoặc phí lưu trữ theo thời gian.
  - Hàm `cache_is_worth_it(avg_reads, write_cost, read_discount, base_price)` tính toán điểm hòa vốn:
    $$\text{Break-even Reads} = \frac{\text{Write Cost}}{\text{Base Price} \times (1 - \text{Read Discount})} = \frac{1.25 \times P_{in}}{P_{in} \times 0.90} \approx 1.39\times$$
- **Kết quả đo lường:** Một tiền tố prompt chỉ cần được đọc lại **≥ 1.39 lần** là sinh lời ròng. Trong tập dữ liệu chat/RAG của NimbusAI, số turn trung bình đạt ~4.0 lần, do đó điều kiện `cache_is_worth_it = True` được thỏa mãn tuyệt đối.

### 4.4 Extension 4: Phân tích Ngân sách & Năng lượng Reasoning
- **Triển khai:** Tại `missions/m2_inference_levers.py` và `missions/m5_report.py`.
- **Phát hiện chấn động:**
  - Số lượng truy vấn reasoning (`is_reasoning=1`) chỉ chiếm **8.4% tổng số request** (201 / 2,400 request).
  - Tuy nhiên, do hiện tượng chuỗi suy nghĩ dài (thinking tokens) và hệ số nhân năng lượng ~80× (`wh_per_query`), nhóm này chiếm **16.5% tổng số token**, **16.5% chi phí inference** và tiêu tốn **29,787.7 Wh/ngày** — tương đương **94.0% tổng năng lượng tiêu thụ toàn hệ thống inference**.
- **Đề xuất Routing:** Đặt ngưỡng tự tin (confidence threshold) hoặc phân loại độ phức tạp task; chỉ kích hoạt reasoning cho 10% các câu hỏi khó nhất, ngăn chặn việc lãng phí tài nguyên cho các câu trả lời cơ bản.

### 4.5 Extension 5: Carbon-Aware Scheduling cho Huấn luyện Ngắt quãng
- **Triển khai:** Tại `missions/m3_purchasing.py`.
- **Cơ chế cải tiến:** Phân tích 4,227 kWh điện năng tiêu thụ mỗi tháng của các job interruptible qua 5 khu vực điện toán đám mây:
  - `us-east-1` (Bắc Virginia): 380 gCO2/kWh | $0.12/kWh → Phát thải 1,606.3 kgCO2e | $507.24 tiền điện.
  - `europe-north1` (Na Uy - Thủy điện): **30 gCO2/kWh** | $0.09/kWh → Phát thải **126.8 kgCO2e** | $380.43 tiền điện.
  - `us-east-wa` (Washington): 90 gCO2/kWh | **$0.055/kWh** → Phát thải 380.4 kgCO2e | **$232.49 tiền điện**.
  - `europe-central2` (Ba Lan - Nhiệt điện than): 660 gCO2/kWh | $0.18/kWh → Phát thải 2,789.8 kgCO2e.
- **Kết quả đo lường:** Điều phối các job huấn luyện sang `europe-north1` giúp giảm **92.1% lượng phát thải carbon** (cắt giảm **1,479.5 kgCO2e / tháng**) mà hoàn toàn không ảnh hưởng đến người dùng cuối do huấn luyện batch không bị ràng buộc bởi độ trễ mạng (RTT).

---

## 5. Khuyến nghị Chiến lược cho NimbusAI (Top 3 Hành Động của FinOps Lead)

Nếu đóng vai trò FinOps Lead tại NimbusAI, 3 hành động tiên quyết tôi sẽ ban hành ngay trong tuần làm việc đầu tiên:

### Hành động 1: Triển khai Tự động hóa "Zero-Waste Policy" (P0 — Ngay trong tuần 1)
- **Hành động cụ thể:** Cài đặt CloudWatch/Prometheus cron alert để tự động shutdown các GPU có mức utilization < 10% liên tục trong 30 phút sau giờ làm việc (xử lý dứt điểm các trường hợp như `gpu-h100-5`). Đồng thời, cấu hình cluster Kubernetes/Slurm để mọi tác vụ training không có SLA khắt khe phải chạy trên Spot Pool với cơ chế tự động checkpoint lưu vào S3/GCS mỗi 30 phút.
- **Tác động dự kiến:** Thu hồi ngay lập tức hơn **$10,640 / tháng** (gồm $600 idle waste và $10,040 chiết khấu spot) mà không cần can thiệp vào logic phần mềm.

### Hành động 2: Chuẩn hóa Kiến trúc Inference Gateway (P1 — Tuần 2 đến Tuần 3)
- **Hành động cụ thể:** Tích hợp LiteLLM Proxy hoặc vLLM/TensorRT-LLM Router tại cổng API gateway của NimbusAI:
  1. Cấu hình tự động gán `prompt_caching` cho tất cả system prompt dài > 1,024 tokens.
  2. Xây dựng bộ phân loại routing 2 tầng (Cascading Classifier): 80% câu hỏi thông thường chuyển sang mô hình nhỏ gọn (Llama-3-8B / Claude 3.5 Haiku / GPT-4o-mini), chỉ các task coding/toán học phức tạp mới mở khóa mô hình lớn.
  3. Áp dụng trần ngân sách cho truy vấn Reasoning (ngăn chặn tình trạng 8.4% request "đốt" 94% năng lượng).
- **Tác động dự kiến:** Cắt giảm **82.6% chi phí inference**, đưa chi phí phục vụ xuống ngưỡng siêu cạnh tranh **$1.126 / 1M-token**.

### Hành động 3: Kích hoạt Chargeback trên nền tảng chuẩn FOCUS (P2 — Tháng thứ 2)
- **Hành động cụ thể:** Do hệ thống hiện tại đã đạt **Tag Coverage 92%** (vượt ngưỡng yêu cầu 80% của FinOps Foundation), chúng tôi sẽ chuyển từ giai đoạn *Showback* (chỉ gửi báo cáo cảnh báo) sang **Chargeback** (thực sự trừ chi phí vào ngân sách của từng phòng ban: Assistant, Search, Eval, RAG) dựa trên dữ liệu chuẩn hóa `outputs/focus_export.csv`.
- **Tác động dự kiến:** Tạo động lực kinh tế trực tiếp cho các Product Manager và Tech Lead tự giác tối ưu prompt, dọn dẹp sandbox thừa thãi và lựa chọn model phù hợp cho tính năng của mình.

---

## 6. Danh mục File Bàn giao & Kiểm tra Nghiệm thu
Tất cả các tài liệu và mã nguồn nghiệm thu đã sẵn sàng trong kho lưu trữ:
- `verify.py`: **11/11 checks passed** (PASS 100%)
- `pytest`: **19 tests passed** (15 unit test gốc + 4 test mở rộng)
- `outputs/report.md`: Báo cáo chi tiết định dạng Markdown
- `outputs/savings.png`: Biểu đồ cột thể hiện mức tiết kiệm theo từng đòn bẩy
- `outputs/focus_export.csv`: Dữ liệu phân bổ chi phí theo chuẩn FOCUS 1.x (50 records mẫu)
- `WRITEUP.md` & `outputs/writeup.md`: Toàn văn bài viết phân tích kỹ thuật và tài chính
