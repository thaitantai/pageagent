# Community Affiliate Page

## Muc tieu

Page kieu `community_affiliate` uu tien gia tri cong dong truoc, affiliate la lop kiem tien phia sau. Research Agent chi de xuat offer khi topic co loi ich ro cho nguoi doc va co metadata de Writer/Approval tranh hard-sell.

## Page context de xuat

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
```

## Cach Research Agent dung context

- Doc `affiliate_offers` truoc `products_services` de tao buying guide, comparison, checklist, red flags va FAQ.
- Gan `community_first` de downstream hieu topic phai uu tien gia tri cong dong.
- Gan `affiliate_disclosure_required` neu policy yeu cau disclosure.
- Gan `claim_guard_required` va `risk_level=medium` khi offer co `do_not_claim`.
- Dung `industry_focus`, `customer_pain_points`, `benefits`, `proof_points`, `competitors` de tao research query va topic score.

## Nguyen tac noi dung

- Bai viet nen bat dau tu van de nguoi mua, khong bat dau tu link.
- Neu co gioi thieu san pham, can co ly do phu hop va disclosure affiliate.
- Bai so sanh nen noi ro ai phu hop voi ai, khong tuyen bo mot san pham tot nhat cho moi nguoi.
- Claim nhay cam ve suc khoe, tai chinh, me va be, my pham can nguon va guardrail ro.
