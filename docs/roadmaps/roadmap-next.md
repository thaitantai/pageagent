# Roadmap giai đoạn phát triển tiếp theo

Du an hien o trang thai beta san sang van hanh noi bo: agent da co pipeline tu nghien cuu, lap ke hoach, viet caption, duyet, xuat ban, cham soc binh luan, bao cao va co harness kiem soat hanh dong nhay cam. Giai doan tiep theo khong phai lam lai tu dau, ma la bien he thong hien co thanh mot san pham van hanh on dinh, do duoc hieu qua va mo rong duoc cho nhieu fanpage.

## Mục tiêu sản phẩm

Trong 6-8 tuan toi, Fanpage Agent can tro thanh mot "tro ly van hanh fanpage" co the chay hang ngay voi it giam sat hon, nhung van giu nguoi that o cac diem quyet dinh quan trong nhu duyet noi dung, xuat ban, tra loi nhay cam va thay doi chien dich.

## Phase 1: Dọn dẹp nền tảng và tăng khả năng quan sát

Mục tiêu: người vận hành biết hệ thống đang ở đâu, da lam gi, co loi gi va co can can thiep khong.

Kết quả mong muốn:

- Chi con mot runtime/package duy nhat `fanpage_agent`.
- Tai lieu, lenh CLI, Docker va cron khong con goi theo phien ban cu.
- Co trang thai roadmap/ops de xem nhanh he thong dang o giai doan nao.
- Audit harness duoc dung nhu nhat ky an toan cho cac hanh dong nhay cam.

Việc cần làm:

- Cập nhật README theo tên sản phẩm hiện tại.
- Thêm `roadmap-status` để xem phase hiện tại từ CLI.
- Chuẩn hóa hướng dẫn chạy local, Docker, cron và duyệt nội dung.
- Thêm smoke test cho các lệnh operator quan trọng.

## Phase 2: An toàn publish và approval thật

Mục tiêu: agent có thể đề xuất và chuẩn bị nội dung tốt, nhung cac hanh dong anh huong that den fanpage phai co vong duyet ro rang.

Kết quả mong muốn:

- Mọi hành động publish/delete/reply nhạy cảm đều có approval record.
- Người vận hành có thể approve/reject từ queue rõ ràng.
- Có audit để biết ai duyệt, lúc nào, nội dung nào.
- Có chế độ dry-run/deploy thật tách bạch.

Việc cần làm:

- Nối approval CLI hiện có vào harness policy sâu hơn.
- Thêm reason code khi bị block hoặc cần approve.
- Tách action auto-reply bình thường và reply nhạy cảm.
- Thêm cảnh báo nếu token/API/cron chưa cấu hình đúng.

## Phase 3: Chất lượng nội dung và học từ hiệu quả

Mục tiêu: agent không chỉ tạo bài đều, mà ngày càng hiểu fanpage nào đang có hiệu quả.

Kết quả mong muốn:

- Mỗi bài đăng có liên kết giữa kế hoạch, caption, publish record và metric.
- Agent biết loại hook, trụ cột nội dung và CTA nào đang tốt.
- Báo cáo tuần đưa ra đề xuất hành động, không chỉ thống kê.

Việc cần làm:

- Chuẩn hóa schema cho content calendar, post history và metrics.
- Thêm score cho caption trước khi đưa vào queue.
- Cải thiện analyst để sinh insight và next actions.
- Thêm evaluation set cho tone, brand fit, CTA và risk.

## Phase 4: Vận hành nhiều fanpage và nhiều chiến dịch

Mục tiêu: một hệ thống có thể quản lý nhiều page/campaign ma khong lan du lieu, lich va giong thuong hieu.

Kết quả mong muốn:

- Mỗi page/brand có cấu hình, lịch, metric và memory riêng.
- Có dashboard/báo cáo gộp nhóm theo page.
- Round-robin hoặc ưu tiên page được cấu hình rõ ràng.

Việc cần làm:

- Chuẩn hóa config nhiều page.
- Tách store theo brand/page.
- Thêm command kiểm tra sức khỏe từng page.
- Thêm test cho routing và dữ liệu không bị chéo.

## Phase 5: Release sản phẩm nội bộ

Mục tiêu: chạy ổn định như một công cụ nội bộ, co tai lieu va quy trinh xu ly su co.

Kết quả mong muốn:

- Deploy lặp lại được.
- Có checklist release.
- Có cảnh báo khi job stale, token lỗi, queue tồn đọng hoac metric khong cap nhat.
- Có tài liệu non-tech cho người vận hành.

Việc cần làm:

- Thêm runbook sự cố.
- Thêm changelog/release checklist.
- Thêm health check CI nếu có pipeline GitHub Actions.
- Rà soát lại Git history/secret nếu repo public.

## Phase 6: Research Intelligence độc lập và dùng chung

Mục tiêu: Research Agent có thể chạy như một công đoạn riêng, tao goi insight co schema on dinh de Planner, Writer va nguoi van hanh cung doc duoc.

Kết quả mong muốn:

- Mỗi lần research sinh ra một `ResearchPacket` co id, thoi gian, source file, confidence, evidence va topic score.
- Có CLI độc lập để chạy research mà không cần chạy toàn bộ pipeline.
- Output lưu thành JSON để cron, dashboard hoặc agent khác đọc lại.
- Planner/Writer có thể ưu tiên chủ đề dựa trên score thay vì chọn thủ công.

Việc cần làm:

- Thêm schema `ResearchPacket`.
- Thêm service build/save packet từ dữ liệu hiện có.
- Thêm CLI `research-standalone` có chế độ offline/deterministic.
- Thêm test cho packet và CLI output.

## Ưu tiên thực thi ngay

1. Hoan tat ResearchPacket va CLI `research-standalone`.
2. Giu `research-brief` legacy chay nhu cu de khong pha workflow hien tai.
3. Dua `topic_scores`, `evidence`, `confidence_score` thanh input uu tien cho Planner/Writer.
4. Ket noi `run-daily` va `deliver-daily-packet` voi ResearchPacket de daily ops co artifact nghien cuu chung.
5. Sau do moi toi uu content scoring va multi-page sau, tranh mo rong khi Research chua co output dung chung.

## Tiến độ thực thi

- 2026-06-06: Đã thêm ResearchPacket độc lập, `research-standalone`, `page-status` va test CLI.
- 2026-06-06: Đã nối `run-daily`/`deliver-daily-packet` sang ResearchPacket, van giu `research_brief` trong payload de khong pha workflow cu, dong thoi luu artifact `research_packet` khi `--save`.
- 2026-06-06: Đã thêm Source Registry va SourceDocument nen ResearchPacket co the ghi nhan nguon dang tin theo page/topic qua `--source-registry-file`.
- 2026-06-06: Đã thêm ScraplingSourceCollector opt-in qua `--fetch-source-documents`, co cache `--source-cache-dir` de ResearchPacket luu noi dung nguon that khi can.
- 2026-06-06: Đã thêm Evidence & Insight Extractor va Research Quality Gate de bien SourceDocument thanh evidence co `source_id`/`trust_score` va canh bao chat luong.
- 2026-06-06: Đã nâng format Research Brief cho operator thay duoc confidence, so nguon, source-backed insights va quality warnings ngay trong digest.
- 2026-06-06: Đã thêm Community Affiliate context de page uu tien gia tri cong dong, doc `affiliate_offers`, gan disclosure/risk metadata va tao topic buying guide/comparison/checklist thay vi hard-sell.
- 2026-06-07: Hoàn thiện ResearchPacket handoff gate voi `status`, `gate_reasons` va `handoff_policy` de downstream biet khi nao chi duoc tao checklist/cau hoi, khi nao can human review va khi nao moi duoc viet claim/recommendation.
