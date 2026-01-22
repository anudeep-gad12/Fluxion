"""Unit tests for GAIA dataset loader.

Tests dataset loading with mocked HuggingFace API.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.gaia.loader import GAIAQuestion, HAS_DATASETS
import scripts.gaia.loader as loader_module


class TestGAIAQuestion:
    """Tests for GAIAQuestion dataclass."""

    def test_basic_question(self):
        """Creates basic question."""
        q = GAIAQuestion(
            task_id="test-001",
            question="What is the capital of France?",
            level=1,
            final_answer="Paris",
        )
        assert q.task_id == "test-001"
        assert q.question == "What is the capital of France?"
        assert q.level == 1
        assert q.final_answer == "Paris"
        assert q.has_attachment is False

    def test_question_with_attachment(self):
        """Creates question with attachment."""
        q = GAIAQuestion(
            task_id="test-002",
            question="Analyze the attached image",
            level=2,
            final_answer="Blue",
            file_name="image.png",
            file_path="2023/validation/image.png",
            has_attachment=True,
        )
        assert q.has_attachment is True
        assert q.file_name == "image.png"


class TestLoadGaiaDataset:
    """Tests for load_gaia_dataset function."""

    def test_missing_datasets_library(self):
        """Raises ImportError when datasets library not installed."""
        # Save original value
        original_has_datasets = loader_module.HAS_DATASETS

        # Simulate missing library
        loader_module.HAS_DATASETS = False

        try:
            with pytest.raises(ImportError, match="datasets library required"):
                loader_module.load_gaia_dataset()
        finally:
            # Restore
            loader_module.HAS_DATASETS = original_has_datasets

    @pytest.mark.skipif(not HAS_DATASETS, reason="datasets library not installed")
    def test_invalid_level(self):
        """Raises ValueError for invalid level."""
        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}):
            with pytest.raises(ValueError, match="Invalid level"):
                loader_module.load_gaia_dataset(level=4)

    @pytest.mark.skipif(not HAS_DATASETS, reason="datasets library not installed")
    def test_invalid_split(self):
        """Raises ValueError for invalid split."""
        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}):
            with pytest.raises(ValueError, match="Invalid split"):
                loader_module.load_gaia_dataset(split="train")

    @pytest.mark.skipif(not HAS_DATASETS, reason="datasets library not installed")
    def test_missing_hf_token(self):
        """Raises EnvironmentError when HF_TOKEN not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(EnvironmentError, match="HF_TOKEN"):
                loader_module.load_gaia_dataset()

    @pytest.mark.skipif(not HAS_DATASETS, reason="datasets library not installed")
    @patch("scripts.gaia.loader.load_dataset")
    def test_loads_dataset_success(self, mock_load_dataset):
        """Successfully loads dataset with mock data."""
        # Mock dataset response
        mock_data = [
            {
                "task_id": "gaia-001",
                "Question": "What is 2+2?",
                "Level": 1,
                "Final answer": "4",
                "file_name": None,
                "file_path": None,
            },
            {
                "task_id": "gaia-002",
                "Question": "Capital of France?",
                "Level": 1,
                "Final answer": "Paris",
                "file_name": None,
                "file_path": None,
            },
        ]
        mock_load_dataset.return_value = mock_data

        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}):
            questions = loader_module.load_gaia_dataset(level=1, split="validation")

        assert len(questions) == 2
        assert questions[0].task_id == "gaia-001"
        assert questions[0].question == "What is 2+2?"
        assert questions[0].final_answer == "4"
        assert questions[1].task_id == "gaia-002"
        assert questions[1].final_answer == "Paris"

    @pytest.mark.skipif(not HAS_DATASETS, reason="datasets library not installed")
    @patch("scripts.gaia.loader.load_dataset")
    def test_skips_attachments(self, mock_load_dataset):
        """Skips questions with attachments when skip_attachments=True."""
        mock_data = [
            {
                "task_id": "gaia-001",
                "Question": "Simple question",
                "Level": 1,
                "Final answer": "answer1",
                "file_name": None,
                "file_path": None,
            },
            {
                "task_id": "gaia-002",
                "Question": "Question with file",
                "Level": 1,
                "Final answer": "answer2",
                "file_name": "doc.pdf",
                "file_path": "2023/validation/doc.pdf",
            },
        ]
        mock_load_dataset.return_value = mock_data

        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}):
            questions = loader_module.load_gaia_dataset(level=1, skip_attachments=True)

        assert len(questions) == 1
        assert questions[0].task_id == "gaia-001"

    @pytest.mark.skipif(not HAS_DATASETS, reason="datasets library not installed")
    @patch("scripts.gaia.loader.load_dataset")
    def test_includes_attachments(self, mock_load_dataset):
        """Includes questions with attachments when skip_attachments=False."""
        mock_data = [
            {
                "task_id": "gaia-001",
                "Question": "Simple question",
                "Level": 1,
                "Final answer": "answer1",
                "file_name": None,
                "file_path": None,
            },
            {
                "task_id": "gaia-002",
                "Question": "Question with file",
                "Level": 1,
                "Final answer": "answer2",
                "file_name": "doc.pdf",
                "file_path": "2023/validation/doc.pdf",
            },
        ]
        mock_load_dataset.return_value = mock_data

        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}):
            questions = loader_module.load_gaia_dataset(level=1, skip_attachments=False)

        assert len(questions) == 2
        assert questions[1].has_attachment is True


class TestGetDatasetStats:
    """Tests for get_dataset_stats function."""

    @patch.object(loader_module, "load_gaia_dataset")
    def test_calculates_stats(self, mock_load):
        """Calculates dataset statistics."""
        mock_load.return_value = [
            GAIAQuestion("1", "Q1", 1, "A1", has_attachment=False),
            GAIAQuestion("2", "Q2", 1, "A2", has_attachment=True),
            GAIAQuestion("3", "Q3", 1, "A3", has_attachment=False),
        ]

        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}):
            stats = loader_module.get_dataset_stats(level=1, split="validation")

        assert stats["total_questions"] == 3
        assert stats["with_attachments"] == 1
        assert stats["without_attachments"] == 2
