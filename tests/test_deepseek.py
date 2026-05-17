"""Tests for DeepSeek provider integration."""

import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from save_token.providers.deepseek import Provider, PROVIDER_CONFIG
from save_token.providers.base import AskResult


logging.basicConfig(level=logging.DEBUG)


class TestDeepSeekProvider:
    """Test cases for DeepSeek provider."""

    def test_provider_config(self):
        """Test that PROVIDER_CONFIG has correct values."""
        cfg = PROVIDER_CONFIG
        
        assert cfg.name == "deepseek"
        assert cfg.url == "https://chat.deepseek.com/"
        assert cfg.input_selector == "textarea"
        assert cfg.send_method == "keys"
        assert cfg.post_send_wait == 30
        assert cfg.session_name == "save-token-ds"

    @patch("save_token.providers.deepseek.OpenCLIBridge")
    def test_ask_basic(self, mock_bridge_class):
        """Test basic ask functionality."""
        mock_bridge = Mock()
        mock_bridge_class.return_value = mock_bridge
        
        mock_bridge.navigate_and_wait.return_value = {"ok": True}
        mock_bridge.fill.return_value = {"filled": True}
        mock_bridge.keys.return_value = {"ok": True}
        mock_bridge.eval.return_value = "Test answer"
        
        provider = Provider()
        result = provider.ask("Hello")
        
        assert isinstance(result, AskResult)
        assert result.question == "Hello"
        assert provider.bridge.navigate_and_wait.called
        assert provider.bridge.fill.called
        assert provider.bridge.keys.called

    @patch("save_token.providers.deepseek.OpenCLIBridge")
    def test_ask_with_deep_think(self, mock_bridge_class):
        """Test ask with deep_think option."""
        mock_bridge = Mock()
        mock_bridge_class.return_value = mock_bridge
        
        mock_bridge.navigate_and_wait.return_value = {"ok": True}
        mock_bridge.fill.return_value = {"filled": True}
        mock_bridge.keys.return_value = {"ok": True}
        mock_bridge.eval.return_value = "Test answer"
        mock_bridge.wait.return_value = None
        
        provider = Provider()
        
        class MockOptions:
            deep_think = True
            web_search = True
            file_paths = None
        
        result = provider.ask("Hello", options=MockOptions())
        
        assert isinstance(result, AskResult)
        assert mock_bridge.eval.call_count > 1

    @patch("save_token.providers.deepseek.OpenCLIBridge")
    def test_ask_with_files(self, mock_bridge_class):
        """Test ask with file upload."""
        mock_bridge = Mock()
        mock_bridge_class.return_value = mock_bridge
        
        mock_bridge.navigate_and_wait.return_value = {"ok": True}
        mock_bridge._run.return_value = {"uploaded": True}
        mock_bridge.fill.return_value = {"filled": True}
        mock_bridge.keys.return_value = {"ok": True}
        mock_bridge.eval.return_value = "Test answer"
        mock_bridge.wait.return_value = None
        
        provider = Provider()
        
        class MockOptions:
            deep_think = False
            web_search = False
            file_paths = ["test.txt"]
        
        result = provider.ask("Analyze this", options=MockOptions())
        
        assert isinstance(result, AskResult)
        assert mock_bridge._run.called

    @patch("save_token.providers.deepseek.OpenCLIBridge")
    def test_apply_options(self, mock_bridge_class):
        """Test option application."""
        mock_bridge = Mock()
        mock_bridge_class.return_value = mock_bridge
        mock_bridge.eval.return_value = "dt:on"
        mock_bridge.wait.return_value = None
        
        provider = Provider()
        
        class MockOptions:
            deep_think = True
            web_search = False
        
        provider._apply_options("test_session", MockOptions())
        
        assert mock_bridge.eval.call_count == 2

    def test_extract_answer_simple(self):
        """Test answer extraction logic."""
        provider = Provider()
        
        raw = "Victor\nHello\nThis is the answer\n深度思考\n"
        result = provider._extract_answer(raw, "Hello")
        
        assert "This is the answer" in result

    def test_extract_answer_with_thinking(self):
        """Test answer extraction with thinking mode."""
        provider = Provider()
        
        raw = "Victor\nQuestion\n已思考 1234\nThinking content\n深度思考\nFinal answer\n"
        result = provider._extract_answer(raw, "Question")
        
        assert "Final answer" in result or "Thinking content" in result

    def test_unique_session(self):
        """Test unique session generation."""
        provider = Provider()
        
        session1 = provider._unique_session()
        session2 = provider._unique_session()
        
        assert session1 != session2
        assert "save-token-ds-" in session1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])