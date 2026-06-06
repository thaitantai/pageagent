# Roadmap giai doan phat trien tiep theo

Du an hien o trang thai beta san sang van hanh noi bo: agent da co pipeline tu nghien cuu, lap ke hoach, viet caption, duyet, xuat ban, cham soc binh luan, bao cao va co harness kiem soat hanh dong nhay cam. Giai doan tiep theo khong phai lam lai tu dau, ma la bien he thong hien co thanh mot san pham van hanh on dinh, do duoc hieu qua va mo rong duoc cho nhieu fanpage.

## Muc tieu san pham

Trong 6-8 tuan toi, Fanpage Agent can tro thanh mot "tro ly van hanh fanpage" co the chay hang ngay voi it giam sat hon, nhung van giu nguoi that o cac diem quyet dinh quan trong nhu duyet noi dung, xuat ban, tra loi nhay cam va thay doi chien dich.

## Phase 1: Don dep nen tang va tang kha nang quan sat

Muc tieu: nguoi van hanh biet he thong dang o dau, da lam gi, co loi gi va co can can thiep khong.

Ket qua mong muon:
- Chi con mot runtime/package duy nhat `fanpage_agent`.
- Tai lieu, lenh CLI, Docker va cron khong con goi theo phien ban cu.
- Co trang thai roadmap/ops de xem nhanh he thong dang o giai doan nao.
- Audit harness duoc dung nhu nhat ky an toan cho cac hanh dong nhay cam.

Viec can lam:
- Cap nhat README theo ten san pham hien tai.
- Them `roadmap-status` de xem phase hien tai tu CLI.
- Chuan hoa huong dan chay local, Docker, cron va duyet noi dung.
- Them smoke test cho cac lenh operator quan trong.

## Phase 2: An toan publish va approval that

Muc tieu: agent co the de xuat va chuan bi noi dung tot, nhung cac hanh dong anh huong that den fanpage phai co vong duyet ro rang.

Ket qua mong muon:
- Moi hanh dong publish/delete/reply nhay cam deu co approval record.
- Nguoi van hanh co the approve/reject tu queue ro rang.
- Co audit de biet ai duyet, luc nao, noi dung nao.
- Co che do dry-run/deploy that tach bach.

Viec can lam:
- Noi approval CLI hien co vao harness policy sau hon.
- Them reason code khi bi block hoac can approve.
- Tach action auto-reply binh thuong va reply nhay cam.
- Them canh bao neu token/API/cron chua cau hinh dung.

## Phase 3: Chat luong noi dung va hoc tu hieu qua

Muc tieu: agent khong chi tao bai deu, ma ngay cang hieu fanpage nao dang co hieu qua.

Ket qua mong muon:
- Moi bai dang co lien ket giua ke hoach, caption, publish record va metric.
- Agent biet loai hook, tru cot noi dung va CTA nao dang tot.
- Bao cao tuan dua ra de xuat hanh dong, khong chi thong ke.

Viec can lam:
- Chuan hoa schema cho content calendar, post history va metrics.
- Them score cho caption truoc khi dua vao queue.
- Cai thien analyst de sinh insight va next actions.
- Them evaluation set cho tone, brand fit, CTA va risk.

## Phase 4: Van hanh nhieu fanpage va nhieu chien dich

Muc tieu: mot he thong co the quan ly nhieu page/campaign ma khong lan du lieu, lich va giong thuong hieu.

Ket qua mong muon:
- Moi page/brand co cau hinh, lich, metric va memory rieng.
- Co dashboard/bao cao gom nhom theo page.
- Round-robin hoac uu tien page duoc cau hinh ro rang.

Viec can lam:
- Chuan hoa config nhieu page.
- Tach store theo brand/page.
- Them command kiem tra suc khoe tung page.
- Them test cho routing va du lieu khong bi cheo.

## Phase 5: Release san pham noi bo

Muc tieu: chay on dinh nhu mot cong cu noi bo, co tai lieu va quy trinh xu ly su co.

Ket qua mong muon:
- Deploy lap lai duoc.
- Co checklist release.
- Co canh bao khi job stale, token loi, queue ton dong hoac metric khong cap nhat.
- Co tai lieu non-tech cho nguoi van hanh.

Viec can lam:
- Them runbook su co.
- Them changelog/release checklist.
- Them health check CI neu co pipeline GitHub Actions.
- Rasoat lai Git history/secret neu repo public.

## Phase 6: Research Intelligence doc lap va dung chung

Muc tieu: Research Agent co the chay nhu mot cong doan rieng, tao goi insight co schema on dinh de Planner, Writer va nguoi van hanh cung doc duoc.

Ket qua mong muon:
- Moi lan research sinh ra mot `ResearchPacket` co id, thoi gian, source file, confidence, evidence va topic score.
- Co CLI doc lap de chay research ma khong can chay toan bo pipeline.
- Output luu thanh JSON de cron, dashboard hoac agent khac doc lai.
- Planner/Writer co the uu tien chu de dua tren score thay vi chon thu cong.

Viec can lam:
- Them schema `ResearchPacket`.
- Them service build/save packet tu du lieu hien co.
- Them CLI `research-standalone` co che do offline/deterministic.
- Them test cho packet va CLI output.

## Uu tien thuc thi ngay

1. Hoan tat ResearchPacket va CLI `research-standalone`.
2. Giu `research-brief` legacy chay nhu cu de khong pha workflow hien tai.
3. Dua `topic_scores`, `evidence`, `confidence_score` thanh input uu tien cho Planner/Writer.
4. Ket noi `run-daily` va `deliver-daily-packet` voi ResearchPacket de daily ops co artifact nghien cuu chung.
5. Sau do moi toi uu content scoring va multi-page sau, tranh mo rong khi Research chua co output dung chung.

## Tien do thuc thi

- 2026-06-06: Da them ResearchPacket doc lap, `research-standalone`, `page-status` va test CLI.
- 2026-06-06: Da noi `run-daily`/`deliver-daily-packet` sang ResearchPacket, van giu `research_brief` trong payload de khong pha workflow cu, dong thoi luu artifact `research_packet` khi `--save`.
