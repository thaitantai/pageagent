from pathlib import Path
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from fanpage_agent.adapters.llm_client import MockLLMClient, OpenAICompatibleClient, build_llm_client
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.models import ResearchBrief


class MockLlmClientTest(unittest.TestCase):
    def test_mock_client_generates_weekly_plan(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        client = MockLLMClient()

        plan = client.generate_weekly_plan(profile=profile, start_date="2026-06-01", days=2)

        self.assertEqual(plan.plan_title, "weekly-plan-brand_abc-2026-06-01")
        self.assertEqual(len(plan.days), 2)

    def test_factory_returns_mock_client_for_mock_provider(self) -> None:
        root = Path(__file__).resolve().parents[1]
        settings = Settings.from_env(env={"LLM_PROVIDER": "mock-local"}, root_dir=root, load_dotenv=False)
        client = build_llm_client(settings)
        self.assertIsInstance(client, MockLLMClient)


class FakeHttpResponse:
    def __init__(self, payload: dict | str) -> None:
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, str):
            return self._payload.encode("utf-8")
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def build_http_error(code: int, body: str) -> HTTPError:
    return HTTPError(
        url="https://example.test/v1/chat/completions",
        code=code,
        msg="mock-error",
        hdrs=None,
        fp=io.BytesIO(body.encode("utf-8")),
    )


class OpenAICompatibleClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.profile = load_brand_profile(self.root / "data" / "sample" / "brand_profile.json")
        self.settings = Settings.from_env(
            env={
                "LLM_PROVIDER": "openai-compatible",
                "LLM_MODEL": "gpt-test",
                "LLM_MODEL_CANDIDATES": "fallback-a,fallback-b",
                "LLM_MAX_TOKENS": "900",
                "LLM_BASE_URL": "https://example.test/v1",
                "LLM_API_KEY": "test-key",
            },
            root_dir=self.root,
            load_dotenv=False,
        )

    def test_factory_returns_openai_compatible_client(self) -> None:
        client = build_llm_client(self.settings)
        self.assertIsInstance(client, OpenAICompatibleClient)

    def test_compact_research_payload_uses_current_research_brief_fields(self) -> None:
        payload = OpenAICompatibleClient._compact_research_payload(
            ResearchBrief(
                recommended_objectives=["lead"],
                recommended_pillars=["education"],
                next_angles=["routine tối giản"],
                frequent_questions=["Da thiếu nước thì bắt đầu từ đâu?"],
                campaign_focus=["soi da"],
                overused_topics=["da khô"],
                recommendations=["Ưu tiên câu hỏi thật từ inbox"],
            )
        )

        self.assertEqual(payload["recommended_objectives"], ["lead"])
        self.assertEqual(payload["recommendations"], ["Ưu tiên câu hỏi thật từ inbox"])
        self.assertNotIn("objective_focus", payload)
        self.assertNotIn("trend_keywords", payload)
        self.assertNotIn("trend_clusters", payload)

    def test_compact_research_payload_includes_trend_data(self) -> None:
        """Trend data được inject vào payload khi có trend_keywords/trend_clusters."""
        payload = OpenAICompatibleClient._compact_research_payload(
            ResearchBrief(
                trend_keywords=["dưỡng ẩm", "chống nắng", "retinol", "mụn", "nám"],
                trend_clusters={
                    "dưỡng ẩm": ["Cách chọn kem dưỡng ẩm", "Dưỡng ẩm mùa hè"],
                    "chống nắng": ["Chống nắng đúng cách"],
                },
            )
        )
        self.assertIn("trend_keywords", payload)
        self.assertEqual(payload["trend_keywords"], ["dưỡng ẩm", "chống nắng", "retinol", "mụn", "nám"])
        self.assertIn("trend_clusters", payload)
        self.assertIn("dưỡng ẩm", payload["trend_clusters"])

    def test_weekly_plan_prompt_avoids_days_input_collision_with_output_schema(self) -> None:
        prompt = json.loads(
            OpenAICompatibleClient._weekly_plan_user_prompt(
                profile=self.profile,
                start_date="2026-06-01",
                days=2,
                research_brief=None,
            )
        )

        self.assertEqual(prompt["requested_day_count"], 2)
        top_level_without_requirements = {key: value for key, value in prompt.items() if key != "requirements"}
        self.assertNotIn("days", top_level_without_requirements)
        self.assertIn("array", prompt["requirements"]["days_output_must_be_array"].lower())

    @patch("fanpage_agent.adapters.llm.openai.urlopen")
    def test_openai_client_generates_weekly_plan_from_chat_completion(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "plan_title": "weekly-plan-brand_abc-2026-06-01",
                                    "days": [
                                        {
                                            "date": "2026-06-01",
                                            "pillar": "education",
                                            "objective": "reach",
                                            "topic": "Routine phục hồi da sau treatment",
                                            "angle": "phục hồi da treatment",
                                            "format": "post_short",
                                            "hook": "Routine nào hợp cho da treatment?",
                                            "cta": "Lưu lại để dùng khi cần",
                                            "visual_brief": "Thiết kế tối giản",
                                            "risk_notes": [],
                                        }
                                    ],
                                    "strategy_notes": ["Giữ tone thực tế"],
                                    "gaps_or_assumptions": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        )
        client = OpenAICompatibleClient(self.settings)

        plan = client.generate_weekly_plan(profile=self.profile, start_date="2026-06-01", days=1)

        self.assertEqual(plan.plan_title, "weekly-plan-brand_abc-2026-06-01")
        self.assertEqual(len(plan.days), 1)
        self.assertEqual(plan.days[0].topic, "Routine phục hồi da sau treatment")
        request = mock_urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "gpt-test")
        self.assertEqual(body["max_tokens"], 900)
        self.assertEqual(body["response_format"]["type"], "json_object")
        self.assertTrue(request.full_url.endswith("/chat/completions"))

    @patch("fanpage_agent.adapters.llm.openai.urlopen")
    def test_openai_client_falls_back_to_next_candidate_after_no_endpoint_error(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = [
            build_http_error(404, '{"error":{"message":"No endpoints found for gpt-test"}}'),
            FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "plan_title": "weekly-plan-brand_abc-2026-06-01",
                                        "days": [
                                            {
                                                "date": "2026-06-01",
                                                "pillar": "education",
                                                "objective": "reach",
                                                "topic": "Routine phục hồi da sau treatment",
                                                "angle": "phục hồi da treatment",
                                                "format": "post_short",
                                                "hook": "Routine nào hợp cho da treatment?",
                                                "cta": "Lưu lại để dùng khi cần",
                                                "visual_brief": "Thiết kế tối giản",
                                                "risk_notes": [],
                                            }
                                        ],
                                        "strategy_notes": ["Giữ tone thực tế"],
                                        "gaps_or_assumptions": [],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            ),
        ]
        client = OpenAICompatibleClient(self.settings)

        plan = client.generate_weekly_plan(profile=self.profile, start_date="2026-06-01", days=1)

        self.assertEqual(plan.plan_title, "weekly-plan-brand_abc-2026-06-01")
        self.assertEqual(mock_urlopen.call_count, 2)
        first_body = json.loads(mock_urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        second_body = json.loads(mock_urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(first_body["model"], "gpt-test")
        self.assertEqual(second_body["model"], "fallback-a")

    @patch("fanpage_agent.adapters.llm.openai.urlopen")
    def test_openai_client_extracts_content_from_sse_chat_completion_chunks(self, mock_urlopen) -> None:
        content = json.dumps(
            {
                "topic": "Da thiếu nước",
                "variants": [
                    {
                        "label": "A",
                        "hook": "Dấu hiệu da thiếu nước dễ bỏ qua",
                        "caption": "Đừng chỉ nhìn bề mặt da. Hãy xem tín hiệu thật sự da đang gửi.",
                        "cta": "Nhắn tin để được tư vấn routine phù hợp",
                        "tone_tags": ["thực tế", "nhẹ nhàng"],
                        "visual_brief": "Ảnh checklist tối giản",
                    }
                ],
                "dos": ["Giữ hook cụ thể"],
                "donts": ["Không claim quá mức"],
            },
            ensure_ascii=False,
        )
        split_at = content.index("variants")
        first = content[:split_at]
        second = content[split_at:]
        mock_urlopen.return_value = FakeHttpResponse(
            "\n\n".join(
                [
                    'data: {"choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}',
                    f'data: {json.dumps({"choices": [{"delta": {"content": first}, "finish_reason": None}]}, ensure_ascii=False)}',
                    f'data: {json.dumps({"choices": [{"delta": {"content": second}, "finish_reason": "stop"}]}, ensure_ascii=False)}',
                    "data: [DONE]",
                ]
            )
        )
        client = OpenAICompatibleClient(self.settings)

        package = client.generate_caption_package(
            profile=self.profile,
            topic="Da thiếu nước",
            pillar="education",
            objective="lead",
            fmt="post_short",
        )

        self.assertEqual(package.topic, "Da thiếu nước")
        self.assertEqual(package.variants[0].label, "A")

    @patch("fanpage_agent.adapters.llm.openai.urlopen")
    def test_openai_client_extracts_content_from_json_line_stream_chunks(self, mock_urlopen) -> None:
        first = '{"topic":"Da thiếu nước","variants":[{"label":"A","hook":"Hook A",'
        second = '"caption":"Caption A","cta":"Nhắn tin để được tư vấn routine phù hợp","tone_tags":["thực tế"],"visual_brief":"Brief A"}],"dos":["Do"],"donts":["Dont"]}'
        mock_urlopen.return_value = FakeHttpResponse(
            "\n".join(
                [
                    json.dumps({"choices": [{"delta": {"content": first}}]}, ensure_ascii=False),
                    json.dumps({"choices": [{"delta": {"content": second}}]}, ensure_ascii=False),
                ]
            )
        )
        client = OpenAICompatibleClient(self.settings)

        package = client.generate_caption_package(
            profile=self.profile,
            topic="Da thiếu nước",
            pillar="education",
            objective="lead",
            fmt="post_short",
        )

        self.assertEqual(package.topic, "Da thiếu nước")
        self.assertEqual(package.variants[0].caption, "Caption A")

    @patch("fanpage_agent.adapters.llm.openai.urlopen")
    def test_openai_client_coerces_weekly_plan_string_notes_to_lists(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "plan_title": "weekly-plan-brand_abc-2026-06-01",
                                    "days": [
                                        {
                                            "date": "2026-06-01",
                                            "pillar": "education",
                                            "objective": "reach",
                                            "topic": "Routine phục hồi da sau treatment",
                                            "angle": "phục hồi da treatment",
                                            "format": "post_short",
                                            "hook": "Routine nào hợp cho da treatment?",
                                            "cta": "Lưu lại để dùng khi cần",
                                            "visual_brief": "Thiết kế tối giản",
                                            "risk_notes": "Không hứa hẹn kết quả tuyệt đối.",
                                        }
                                    ],
                                    "strategy_notes": "Giữ tone thực tế.",
                                    "gaps_or_assumptions": "Giả định người đọc là khách hàng mới.",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        )
        client = OpenAICompatibleClient(self.settings)

        plan = client.generate_weekly_plan(profile=self.profile, start_date="2026-06-01", days=1)

        self.assertEqual(plan.days[0].risk_notes, ["Không hứa hẹn kết quả tuyệt đối."])
        self.assertEqual(plan.strategy_notes, ["Giữ tone thực tế."])
        self.assertEqual(plan.gaps_or_assumptions, ["Giả định người đọc là khách hàng mới."])

    @patch("fanpage_agent.adapters.llm.openai.urlopen")
    def test_openai_client_retries_weekly_plan_after_invalid_days_shape(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = [
            FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "plan_title": "weekly-plan-brand_abc-2026-06-01",
                                        "days": 2,
                                        "strategy_notes": "Giữ tone thực tế.",
                                        "gaps_or_assumptions": [],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            ),
            FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "plan_title": "weekly-plan-brand_abc-2026-06-01",
                                        "days": [
                                            {
                                                "date": "2026-06-01",
                                                "pillar": "education",
                                                "objective": "reach",
                                                "topic": "Routine phục hồi da sau treatment",
                                                "angle": "phục hồi da treatment",
                                                "format": "post_short",
                                                "hook": "Routine nào hợp cho da treatment?",
                                                "cta": "Lưu lại để dùng khi cần",
                                                "visual_brief": "Thiết kế tối giản",
                                                "risk_notes": "Không hứa hẹn kết quả tuyệt đối.",
                                            }
                                        ],
                                        "strategy_notes": "Giữ tone thực tế.",
                                        "gaps_or_assumptions": [],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            ),
        ]
        client = OpenAICompatibleClient(self.settings)

        plan = client.generate_weekly_plan(profile=self.profile, start_date="2026-06-01", days=1)

        self.assertEqual(plan.days[0].topic, "Routine phục hồi da sau treatment")
        self.assertEqual(plan.days[0].risk_notes, ["Không hứa hẹn kết quả tuyệt đối."])
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("fanpage_agent.adapters.llm.openai.urlopen")
    def test_openai_client_retries_caption_generation_after_invalid_json(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = [
            FakeHttpResponse({"choices": [{"message": {"content": "not-json"}}]}),
            FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "topic": "Da thiếu nước",
                                        "variants": [
                                            {
                                                "label": "A",
                                                "hook": "Dấu hiệu da thiếu nước dễ bỏ qua",
                                                "caption": "Đừng chỉ nhìn bề mặt da. Hãy xem tín hiệu thật sự da đang gửi.",
                                                "cta": "Nhắn tin để được tư vấn routine phù hợp",
                                                "tone_tags": ["thực tế", "nhẹ nhàng"],
                                                "visual_brief": "Ảnh checklist tối giản",
                                            }
                                        ],
                                        "dos": ["Giữ hook cụ thể"],
                                        "donts": ["Không claim quá mức"],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            ),
        ]
        client = OpenAICompatibleClient(self.settings)

        package = client.generate_caption_package(
            profile=self.profile,
            topic="Da thiếu nước",
            pillar="education",
            objective="lead",
            fmt="post_short",
        )

        self.assertEqual(package.topic, "Da thiếu nước")
        self.assertEqual(package.variants[0].label, "A")
        self.assertEqual(mock_urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
