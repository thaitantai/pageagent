# Community Affiliate Page

## Mục tiêu

Page kiểu `community_affiliate` ưu tiên giá trị cộng đồng trước, affiliate là lớp kiếm tiền phía sau. Research Agent chỉ đề xuất offer khi topic có lợi ích rõ cho người đọc và có metadata để Writer/Approval tránh hard-sell.

## Page context đề xuất

```json
{
  "page_type": "community_affiliate",
  "industry_focus": "do gia dung thong minh",
  "community_value": "giup nguoi mua chon dung theo nhu cau that",
  "audience": "gia dinh tre song o can ho",
  "topic_focus": ["may loc khong khi", "robot hut bui"],
  "customer_pain_points": [
    "khong biet chon san pham theo dien tich phong",
    "so mua nham hang khong phu hop"
  ],
  "affiliate_offers": [
    {
      "name": "May loc khong khi pho thong",
      "category": "may loc khong khi",
      "benefits": ["phu hop phong nho", "gia de tiep can"],
      "proof_points": ["thong so hang", "review nguoi dung"],
      "competitors": ["Mau A", "Mau B"],
      "do_not_claim": ["chua benh ho hap", "loc sach 100% virus"]
    }
  ],
  "content_policy": {
    "affiliate_disclosure_required": true,
    "avoid_hard_sell": true,
    "require_pros_cons": true,
    "require_evidence_before_recommendation": true
  }
}
```text

## Cách Research Agent dùng context

- Đọc `affiliate_offers` trước `products_services` de tao buying guide, comparison, checklist, red flags va FAQ.
- Gắn `community_first` để downstream hiểu topic phải ưu tiên giá trị cộng đồng.
- Gắn `affiliate_disclosure_required` nếu policy yêu cầu disclosure.
- Gắn `claim_guard_required` và `risk_level=medium` khi offer có `do_not_claim`.
- Dùng `industry_focus`, `customer_pain_points`, `benefits`, `proof_points`, `competitors` để tạo research query và topic score.

## Nguyên tắc nội dung

- Bài viết nên bắt đầu từ vấn đề người mua, không bắt đầu từ link.
- Nếu có giới thiệu sản phẩm, cần có lý do phù hợp và disclosure affiliate.
- Bài so sánh nên nói rõ ai phù hợp với ai, không tuyên bố một sản phẩm tốt nhất cho mọi người.
- Claim nhạy cảm về sức khỏe, tài chính, mẹ và bé, mỹ phẩm cần nguồn và guardrail rõ.
