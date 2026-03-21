"""Tests for Instagram/Threads link detection handler."""

from __future__ import annotations

import pytest

from bot.handlers.link_detector import parse_social_links
from bot.services.oembed import extract_hashtags


# ---------------------------------------------------------------------------
# URL parsing tests
# ---------------------------------------------------------------------------


class TestParseInstagramLinks:
    def test_profile_basic(self):
        links = parse_social_links("https://instagram.com/aromatherapy_expert")
        assert len(links) == 1
        assert links[0].platform == "instagram"
        assert links[0].link_type == "profile"
        assert links[0].username == "aromatherapy_expert"

    def test_profile_with_www(self):
        links = parse_social_links("https://www.instagram.com/aroma.lab/")
        assert len(links) == 1
        assert links[0].link_type == "profile"
        assert links[0].username == "aroma.lab"

    def test_profile_in_text(self):
        links = parse_social_links("Посмотри этот аккаунт https://instagram.com/wellness_guru, классный контент!")
        assert len(links) == 1
        assert links[0].username == "wellness_guru"

    def test_post(self):
        links = parse_social_links("https://www.instagram.com/p/CxYz123AbC/")
        assert len(links) == 1
        assert links[0].link_type == "post"
        assert links[0].shortcode == "CxYz123AbC"

    def test_reel(self):
        links = parse_social_links("https://instagram.com/reel/ABC123/")
        assert len(links) == 1
        assert links[0].link_type == "post"
        assert links[0].shortcode == "ABC123"

    def test_reels_plural(self):
        links = parse_social_links("https://instagram.com/reels/XYZ789/")
        assert len(links) == 1
        assert links[0].link_type == "post"

    def test_reserved_paths_ignored(self):
        links = parse_social_links("https://instagram.com/explore/")
        assert len(links) == 0

    def test_post_with_query_params(self):
        links = parse_social_links("https://instagram.com/p/ABC123/?igsh=abc")
        assert len(links) == 1
        assert links[0].shortcode == "ABC123"

    def test_no_link(self):
        links = parse_social_links("Привет, как дела?")
        assert len(links) == 0


class TestParseThreadsLinks:
    def test_profile(self):
        links = parse_social_links("https://threads.net/@aroma_lab")
        assert len(links) == 1
        assert links[0].platform == "threads"
        assert links[0].link_type == "profile"
        assert links[0].username == "aroma_lab"

    def test_profile_with_www(self):
        links = parse_social_links("https://www.threads.net/@wellness.guru/")
        assert len(links) == 1
        assert links[0].link_type == "profile"
        assert links[0].username == "wellness.guru"

    def test_post(self):
        links = parse_social_links("https://threads.net/@aroma_lab/post/CxYz123")
        assert len(links) == 1
        assert links[0].link_type == "post"
        assert links[0].username == "aroma_lab"
        assert links[0].shortcode == "CxYz123"

    def test_post_in_sentence(self):
        links = parse_social_links("Вот интересный пост https://threads.net/@user1/post/ABC123 что думаешь?")
        assert len(links) == 1
        assert links[0].username == "user1"
        assert links[0].shortcode == "ABC123"


class TestMixedLinks:
    def test_multiple_links(self):
        text = "IG: https://instagram.com/user1 и Threads: https://threads.net/@user2"
        links = parse_social_links(text)
        assert len(links) == 2

    def test_text_with_no_links(self):
        links = parse_social_links("Обычное сообщение без ссылок #ароматерапия")
        assert len(links) == 0


# ---------------------------------------------------------------------------
# Hashtag extraction tests
# ---------------------------------------------------------------------------


class TestExtractHashtags:
    def test_basic(self):
        assert extract_hashtags("Hello #world #test") == ["world", "test"]

    def test_cyrillic(self):
        tags = extract_hashtags("#ароматерапия #эфирныемасла")
        assert tags == ["ароматерапия", "эфирныемасла"]

    def test_dedup(self):
        tags = extract_hashtags("#Test #test #TEST")
        assert tags == ["test"]

    def test_mixed(self):
        tags = extract_hashtags("Post about #wellness and #Ароматерапия #wellness")
        assert tags == ["wellness", "ароматерапия"]

    def test_no_hashtags(self):
        assert extract_hashtags("No tags here") == []

    def test_empty(self):
        assert extract_hashtags("") == []
