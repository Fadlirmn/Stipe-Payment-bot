import unittest
from unittest.mock import MagicMock
from bot.postgres_db import PooledConnectionWrapper

class TestConnectionPool(unittest.TestCase):
    def test_pooled_connection_wrapper_closes_and_returns_to_pool(self):
        mock_conn = MagicMock()
        mock_pool = MagicMock()
        
        # Initialize wrapper
        wrapper = PooledConnectionWrapper(mock_conn, mock_pool)
        
        # Verify delegates work
        wrapper.commit()
        mock_conn.commit.assert_called_once()
        
        # Verify close returns to pool
        wrapper.close()
        mock_pool.putconn.assert_called_once_with(mock_conn)
        
    def test_pooled_connection_wrapper_context_manager(self):
        mock_conn = MagicMock()
        mock_pool = MagicMock()
        
        with PooledConnectionWrapper(mock_conn, mock_pool) as conn:
            conn.commit()
            
        mock_conn.commit.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)

if __name__ == '__main__':
    unittest.main()
