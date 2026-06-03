from __future__ import annotations

import unittest

from fanpage_agent.models import TrendItem
from fanpage_agent.scraping.trend_analyzer import (
    SKINCARE_KEYWORDS,
    VN_STOPWORDS,
    TrendAnalyzer,
)


class TrendAnalyzerTest(unittest.TestCase):
    """Test TrendAnalyzer với dữ liệu mẫu skincare/healthcare VN."""

    def setUp(self) -> None:
        self.sample_trends: list[TrendItem] = [
            TrendItem(
                title="Quy tắc vàng khi chọn kem dưỡng ẩm cho da mụn",
                source="24h - Làm đẹp",
                url="https://example.com/1",
                snippet="",
            ),
            TrendItem(
                title="Vì sao mùa hè là thời điểm dễ lão hóa da?",
                source="24h - Làm đẹp",
                url="https://example.com/2",
                snippet="",
            ),
            TrendItem(
                title="Retinol cho người mới bắt đầu: hướng dẫn chi tiết",
                source="24h - Làm đẹp",
                url="https://example.com/3",
                snippet="",
            ),
            TrendItem(
                title="Chuyên gia gợi ý 7 món ăn sáng giảm mỡ bụng",
                source="24h - Làm đẹp",
                url="https://example.com/4",
                snippet="",
            ),
            TrendItem(
                title="Nên đi ngủ lúc mấy giờ để có làn da đẹp?",
                source="24h - Làm đẹp",
                url="https://example.com/5",
                snippet="",
            ),
            TrendItem(
                title="Ca mắc sởi tăng cao, Bộ Y tế khuyến cáo tiêm vắc xin",
                source="VnExpress - Sức khỏe",
                url="https://example.com/6",
                snippet="",
            ),
            TrendItem(
                title="Cách chọn kem chống nắng cho da dầu mụn mùa hè",
                source="24h - Làm đẹp",
                url="https://example.com/7",
                snippet="",
            ),
            TrendItem(
                title="Collagen có thực sự làm trẻ hóa da?",
                source="Afamily - Sức khỏe",
                url="https://example.com/8",
                snippet="",
            ),
        ]

    # ------------------------------------------------------------------
    # Tokenize
    # ------------------------------------------------------------------

    def test_tokenize_removes_stopwords(self) -> None:
        """Stopword phải được lọc bỏ, từ có nghĩa giữ lại."""
        tokens = TrendAnalyzer._tokenize("Quy tắc vàng khi chọn kem dưỡng ẩm cho da")
        self.assertNotIn("và", tokens)  # stopword
        self.assertNotIn("khi", tokens)  # stopword
        self.assertNotIn("cho", tokens)  # stopword
        self.assertIn("kem", tokens)
        self.assertIn("dưỡng", tokens)
        self.assertIn("da", tokens)

    def test_tokenize_handles_empty(self) -> None:
        """Text rỗng trả về list rỗng."""
        self.assertEqual(TrendAnalyzer._tokenize(""), [])
        self.assertEqual(TrendAnalyzer._tokenize("   "), [])

    # ------------------------------------------------------------------
    # Keyword frequency
    # ------------------------------------------------------------------

    def test_keyword_frequency_counts_titles(self) -> None:
        """Keyword frequency phải đếm đúng các từ nổi bật."""
        analyzer = TrendAnalyzer(self.sample_trends)
        freq = analyzer.keyword_frequency()
        # "da" xuất hiện trong nhiều title
        self.assertGreater(freq.get("da", 0), 1)
        # "kem" xuất hiện ít nhất 2 lần
        self.assertGreaterEqual(freq.get("kem", 0), 2)

    def test_keyword_frequency_no_duplicate_in_title(self) -> None:
        """Mỗi từ chỉ đếm 1 lần/title dù xuất hiện nhiều lần."""
        trends = [
            TrendItem(title="da da da đẹp", source="test"),
        ]
        analyzer = TrendAnalyzer(trends)
        freq = analyzer.keyword_frequency()
        self.assertEqual(freq.get("da", 0), 1)

    # ------------------------------------------------------------------
    # Phrase extraction
    # ------------------------------------------------------------------

    def test_extract_phrases_bigram(self) -> None:
        """Bigram phải phát hiện được cụm 'chọn kem' (xuất hiện 2 lần)."""
        analyzer = TrendAnalyzer(self.sample_trends)
        phrases = analyzer.extract_phrases(min_freq=2)
        phrase_words = {p for p, _ in phrases}
        # "chọn kem" xuất hiện trong 2 title
        self.assertIn("chọn kem", phrase_words, msg="Bigram 'chọn kem' phải được phát hiện (2 lần)")

    def test_extract_phrases_min_freq(self) -> None:
        """Cụm chỉ xuất hiện 1 lần không được trả về khi min_freq=2."""
        analyzer = TrendAnalyzer(self.sample_trends)
        phrases = analyzer.extract_phrases(min_freq=2)
        for phrase, count in phrases:
            self.assertGreaterEqual(count, 2)

    # ------------------------------------------------------------------
    # Relevance scoring
    # ------------------------------------------------------------------

    def test_score_relevance_skincare_scores_high(self) -> None:
        """Trend về skincare phải có điểm relevance > 0."""
        analyzer = TrendAnalyzer(self.sample_trends)
        scores = analyzer.score_relevance()
        # Trend về kem dưỡng ẩm có nhiều từ khóa skincare
        skin_trend_score = scores[0]  # "Quy tắc vàng khi chọn kem dưỡng ẩm cho da mụn"
        self.assertGreater(skin_trend_score, 0.0)

    def test_score_relevance_general_health_lower(self) -> None:
        """Trend sức khỏe tổng quát có điểm thấp hơn skincare."""
        analyzer = TrendAnalyzer(self.sample_trends)
        scores = analyzer.score_relevance()
        skin_score = scores[0]  # skincare
        general_score = scores[5]  # "Ca mắc sởi tăng cao"
        self.assertGreater(skin_score, general_score)

    def test_top_by_relevance_returns_top_n(self) -> None:
        """top_by_relevance trả về đúng số lượng và sắp xếp giảm dần."""
        analyzer = TrendAnalyzer(self.sample_trends)
        top = analyzer.top_by_relevance(n=3)
        self.assertEqual(len(top), 3)
        for i in range(len(top) - 1):
            self.assertGreaterEqual(top[i][2], top[i + 1][2])

    # ------------------------------------------------------------------
    # Clustering
    # ------------------------------------------------------------------

    def test_cluster_has_multiple_groups(self) -> None:
        """Phải có ít nhất 2 cụm chủ đề từ dữ liệu skincare."""
        analyzer = TrendAnalyzer(self.sample_trends)
        clusters = analyzer.cluster(top_n=5)
        self.assertGreaterEqual(len(clusters), 2)

    def test_cluster_skincare_words(self) -> None:
        """Cụm 'da' phải chứa các item về da."""
        analyzer = TrendAnalyzer(self.sample_trends)
        clusters = analyzer.cluster(top_n=10)
        if "da" in clusters:
            titles = [t.title for t in clusters["da"]]
            self.assertTrue(all("da" in t.lower() for t in titles))

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def test_generate_report_structure(self) -> None:
        """Report phải có đủ các trường chính."""
        analyzer = TrendAnalyzer(self.sample_trends)
        report = analyzer.generate_report()
        self.assertIn("total_trends", report)
        self.assertIn("sources", report)
        self.assertIn("top_keywords", report)
        self.assertIn("top_phrases", report)
        self.assertIn("clusters", report)
        self.assertIn("top_relevant", report)
        self.assertEqual(report["total_trends"], len(self.sample_trends))

    # ------------------------------------------------------------------
    # Domain constants
    # ------------------------------------------------------------------

    def test_skincare_keywords_not_empty(self) -> None:
        """SKINCARE_KEYWORDS phải được định nghĩa."""
        self.assertGreater(len(SKINCARE_KEYWORDS), 0)
        self.assertIn("da", SKINCARE_KEYWORDS)
        self.assertIn("kem", SKINCARE_KEYWORDS)
        self.assertIn("retinol", SKINCARE_KEYWORDS)

    def test_vn_stopwords_not_empty(self) -> None:
        """VN_STOPWORDS phải chứa các từ phổ biến."""
        self.assertIn("và", VN_STOPWORDS)
        self.assertIn("của", VN_STOPWORDS)
        self.assertIn("là", VN_STOPWORDS)


if __name__ == "__main__":
    unittest.main()
