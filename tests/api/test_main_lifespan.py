from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app


def test_lifespan_shutdown_calls_upload_queue_shutdown():
    mock_queue = MagicMock()
    mock_reconciliation = MagicMock()

    with patch("main.get_upload_queue_service", return_value=mock_queue):
        with patch("main.get_reconciliation_service", return_value=mock_reconciliation):
            with patch("main.settings") as mock_settings:
                mock_settings.reconcile_on_startup = True
                mock_settings.reconcile_repair_on_startup = False
                with TestClient(app) as client:
                    response = client.get("/health")

    assert response.status_code == 200
    mock_reconciliation.run_report.assert_called_once()
    mock_queue.shutdown.assert_called_once()
