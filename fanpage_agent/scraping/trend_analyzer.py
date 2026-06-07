from __future__ import annotations

import logging
import re
from collections import Counter

from fanpage_agent.models import TrendItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vietnamese stopwords — các từ phổ biến không mang ý nghĩa chủ đề
# ---------------------------------------------------------------------------
VN_STOPWORDS: set[str] = {
    "và", "của", "có", "được", "cho", "các", "là", "trong", "với",
    "một", "những", "đã", "sẽ", "đang", "không", "này", "khi",
    "từ", "đến", "vào", "ra", "lên", "xuống", "qua", "lại", "còn",
    "hoặc", "nếu", "thì", "rất", "nên", "vì", "bị", "do", "hay",
    "ở", "tại", "theo", "sau", "trước", "giữa", "trên", "dưới",
    "vẫn", "đều", "để", "mà", "cùng", "như", "cũng", "nhiều",
    "ít", "hơn", "nhất", "mới", "cũ", "đây", "đó", "ấy", "nào",
    "vậy", "thế", "nhưng", "tuy", "song", "vì", "nên", "bởi",
    "tôi", "bạn", "chúng", "người", "việc", "điều", "khiến",
    "thời", "gian", "mỗi", "năm", "tháng", "ngày", "giờ", "phút",
    "làm", "sao", "gì", "ai", "đâu", "bao", "nhiêu", "nào",
    "lớn", "nhỏ", "cao", "thấp", "dài", "ngắn", "rộng", "hẹp",
    "đầu", "cuối", "bắt", "nguồn", "trong", "khoảng", "khiến",
    "phải", "cần", "thể", "tới", "lại", "vừa", "mất", "hết",
    "đúng", "sai", "thật", "giả", "tốt", "xấu", "xem", "biết",
    "nói", "học", "hỏi", "trả", "lời", "này", "kia", "đi",
    "và", "cả", "hãy", "chỉ", "là", "đó", "và", "trong",
}

# ---------------------------------------------------------------------------
# Domain keywords cho skincare/healthcare GenZ
# ---------------------------------------------------------------------------
SKINCARE_KEYWORDS: set[str] = {
    # Skincare core
    "da", "dưỡng", "ẩm", "kem", "sữa", "rửa", "mặt", "tẩy", "trang",
    "sunscreen", "chống", "nắng", "retinol", "vitamin", "serum",
    "toner", "nước", "hoa", "hồng", "mụn", "trị", "nám", "tàn",
    "nhang", "thâm", "sẹo", "lão", "hóa", "chống", "lão", "hóa",
    "collagen", "elastin", "peptide", "niacinamide", "b3", "aha", "bha",
    "pha", "acid", "salicylic", "glycolic", "hyaluronic", "ha",
    "dầu", "dừa", "olive", "jojoba", "argan", "squalane",
    "mặt", "nạ", "mask", "đắp", "dưỡng", "trắng", "sáng",
    "đều", "màu", "lỗ", "chân", "lông", "se", "khít",
    "tái", "tạo", "phục", "hồi", "cấp", "nước",
    # Làm đẹp
    "đẹp", "làm", "đẹp", "trang", "điểm", "son", "môi",
    "mascara", "eyeliner", "phấn", "nền", "che", "khuyết",
    "tóc", "gội", "xả", "uốn", "nhuộm",
    # Health / cơ thể
    "sức", "khỏe", "bệnh", "thuốc", "điều", "trị", "khám",
    "xét", "nghiệm", "vắc", "xin", "tiêm", "chủng",
    "ăn", "uống", "dinh", "dưỡng", "thực", "phẩm", "calo",
    "giảm", "cân", "mỡ", "bụng", "tập", "thể", "dục",
    "yoga", "gym", "chạy", "bộ", "đi", "bộ",
    # GenZ / teen
    "genz", "gen", "z", "teen", "trẻ", "sinh", "viên",
    "học", "đường", "xu", "hướng", "trend", "viral",
}


class TrendAnalyzer:
    """Phân tích trend từ dữ liệu web scraping.

    Hỗ trợ:
    - Trích xuất keyword / phrase từ tiêu đề
    - Gom nhóm chủ đề (topic clustering)
    - Tính điểm relevance cho skincare/healthcare
    - Sinh báo cáo tổng hợp
    """

    def __init__(self, trends: list[TrendItem]) -> None:
        self.trends = trends

    # ------------------------------------------------------------------
    # Tokenizer đơn giản cho tiếng Việt
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tách từ đơn giản: lowercase, lọc ký tự đặc biệt, split."""
        text = text.lower()
        text = re.sub(r"[^a-zàáạãảâấầậẫẩăắằặẵẳèéẹẽẻêếềệễểđìíịĩỉòóọõỏôốồộỗổơớờỡỡởùúụũủưứừựữửỳýỵỹỷ\s]", " ", text)
        words = text.split()
        return [w for w in words if len(w) > 1 and w not in VN_STOPWORDS]

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    def keyword_frequency(self) -> Counter:
        """Đếm tần suất từ xuất hiện trong tất cả tiêu đề.

        Returns
        -------
        Counter
            Từ → số lần xuất hiện (giảm dần)
        """
        counter: Counter = Counter()
        for t in self.trends:
            words = self._tokenize(t.title)
            # Loại bỏ trùng lặp trong cùng 1 title — mỗi từ chỉ đếm 1 lần/title
            unique = set(words)
            counter.update(unique)
        return counter

    def extract_phrases(self, min_freq: int = 2, max_words: int = 3) -> list[tuple[str, int]]:
        """Trích xuất cụm từ (bigram/trigram) từ tiêu đề.

        Parameters
        ----------
        min_freq : int
            Tần suất tối thiểu để xuất hiện trong kết quả.
        max_words : int
            Số từ tối đa trong cụm (2 = bigram, 3 = trigram).

        Returns
        -------
        list[tuple[str, int]]
            Các cụm từ phổ biến nhất (giảm dần theo tần suất).
        """
        all_tokens: list[list[str]] = [self._tokenize(t.title) for t in self.trends]
        counter: Counter = Counter()

        for tokens in all_tokens:
            seen: set[str] = set()
            for n in range(2, max_words + 1):
                for i in range(len(tokens) - n + 1):
                    phrase = " ".join(tokens[i : i + n])
                    if phrase not in seen:
                        seen.add(phrase)
                        counter[phrase] += 1

        return [(p, c) for p, c in counter.most_common() if c >= min_freq]

    # ------------------------------------------------------------------
    # Topic clustering
    # ------------------------------------------------------------------

    def cluster(self, top_n: int = 10) -> dict[str, list[TrendItem]]:
        """Gom nhóm các trend theo chủ đề dựa trên keyword.

        Mỗi cụm được đặt tên bằng keyword phổ biến nhất.
        Một item có thể thuộc nhiều cụm (nếu chứa nhiều keyword).

        Parameters
        ----------
        top_n : int
            Số cụm tối đa trả về.

        Returns
        -------
        dict[str, list[TrendItem]]
            Tên cụm → danh sách TrendItem thuộc cụm đó.
        """
        keywords: list[str] = [w for w, _ in self.keyword_frequency().most_common(20)]

        clusters: dict[str, list[TrendItem]] = {}

        for word in keywords:
            items: list[TrendItem] = []
            for t in self.trends:
                tokens = self._tokenize(t.title)
                if word in tokens:
                    items.append(t)
            if items:
                clusters[word] = items

        # Sort clusters by size, limit, deduplicate
        sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))
        result: dict[str, list[TrendItem]] = {}
        for label, items in sorted_clusters[:top_n]:
            seen: set[int] = set()
            deduped: list[TrendItem] = []
            for item in items:
                if id(item) not in seen:
                    seen.add(id(item))
                    deduped.append(item)
            result[label] = deduped

        return result

    # ------------------------------------------------------------------
    # Relevance scoring
    # ------------------------------------------------------------------

    def score_relevance(self) -> dict[int, float]:
        """Tính điểm relevance cho từng trend dựa trên skincare/health keywords.

        Returns
        -------
        dict[int, float]
            {index_in_self.trends: score_0_1}
        """
        scores: dict[int, float] = {}
        for i, t in enumerate(self.trends):
            tokens = set(self._tokenize(t.title))
            if not tokens:
                scores[i] = 0.0
                continue
            matched = tokens & SKINCARE_KEYWORDS
            score = len(matched) / max(len(tokens), 1)
            # Bonus cho tiêu đề có nhiều từ khóa skincare
            score = min(score * 1.5, 1.0)
            scores[i] = round(score, 2)
        return scores

    def top_by_relevance(self, n: int = 10) -> list[tuple[int, TrendItem, float]]:
        """Top N trend có điểm relevance cao nhất.

        Returns
        -------
        list[tuple[int, TrendItem, float]]
            (index, item, score)
        """
        scores = self.score_relevance()
        ranked = sorted(
            [(i, self.trends[i], scores[i]) for i in range(len(self.trends))],
            key=lambda x: -x[2],
        )
        return ranked[:n]

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def generate_report(self) -> dict:
        """Sinh báo cáo tổng hợp: keywords, cụm chủ đề, top trends.

        Returns
        -------
        dict
            Báo cáo có cấu trúc.
        """
        keywords = self.keyword_frequency().most_common(15)
        phrases = self.extract_phrases(min_freq=2)[:10]
        clusters = self.cluster(top_n=8)
        top_trends = self.top_by_relevance(n=10)

        return {
            "total_trends": len(self.trends),
            "sources": list({t.source for t in self.trends}),
            "top_keywords": [{"word": w, "count": c} for w, c in keywords],
            "top_phrases": [{"phrase": p, "count": c} for p, c in phrases],
            "clusters": {
                label: [t.title for t in items]
                for label, items in clusters.items()
            },
            "top_relevant": [
                {
                    "title": t.title,
                    "source": t.source,
                    "url": t.url,
                    "score": score,
                }
                for _, t, score in top_trends
            ],
        }
