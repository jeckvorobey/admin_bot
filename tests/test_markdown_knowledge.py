"""Тесты markdown-backed FAQ/partners lookup."""

from __future__ import annotations

from pathlib import Path

from app.ai.knowledge import KnowledgeMarkdownStore


def test_markdown_store_loads_frontmatter_and_body(tmp_path: Path) -> None:
    """KnowledgeMarkdownStore должен читать FAQ и partners из `.md` каталога."""
    faq_dir = tmp_path / "faq"
    partner_dir = tmp_path / "partners"
    faq_dir.mkdir()
    partner_dir.mkdir()
    (faq_dir / "exchange.md").write_text(
        """---
id: 11
priority: 3
trigger_words:
  - обмен
  - usdt
link: https://example.com/exchange
---

Ответ из body.
""",
        encoding="utf-8",
    )
    (partner_dir / "rent.md").write_text(
        """---
id: 21
name: Партнёр Б
category: rent
priority: 2
trigger_words:
  - жильё
link: https://example.com/rent
---

Описание из body.
""",
        encoding="utf-8",
    )

    store = KnowledgeMarkdownStore(tmp_path)

    faq = store.load_faq()[0]
    partner = store.load_partners()[0]

    assert faq.id == 11
    assert faq.answer == "Ответ из body."
    assert faq.trigger_words == "обмен,usdt"
    assert partner.id == 21
    assert partner.description == "Описание из body."
    assert partner.trigger_words == "жильё"
