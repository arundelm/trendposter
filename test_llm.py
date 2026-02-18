"""Tests for LLM response parsing."""

from trendposter.llm.base import parse_analysis_response


SAMPLE_TWEETS = [
    {"id": 1, "text": "AI is changing everything"},
    {"id": 2, "text": "Great weather today"},
    {"id": 3, "text": "New Python release is amazing"},
]


def test_parse_valid_response():
    response = '''{
        "best_tweet_id": 1,
        "relevance_score": 82,
        "matched_trend": "AI",
        "reasoning": "AI is trending heavily right now",
        "should_post": true
    }'''
    result = parse_analysis_response(response, SAMPLE_TWEETS)
    assert result is not None
    assert result.tweet_id == 1
    assert result.relevance_score == 82
    assert result.should_post is True


def test_parse_markdown_wrapped():
    response = '''```json
    {
        "best_tweet_id": 3,
        "relevance_score": 65,
        "matched_trend": "Python",
        "reasoning": "Python is trending",
        "should_post": true
    }
    ```'''
    result = parse_analysis_response(response, SAMPLE_TWEETS)
    assert result is not None
    assert result.tweet_id == 3


def test_parse_no_match():
    response = '''{
        "best_tweet_id": null,
        "relevance_score": 10,
        "matched_trend": null,
        "reasoning": "Nothing matches well",
        "should_post": false
    }'''
    result = parse_analysis_response(response, SAMPLE_TWEETS)
    assert result is None


def test_parse_invalid_json():
    result = parse_analysis_response("not json at all", SAMPLE_TWEETS)
    assert result is None
