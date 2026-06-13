# redis_client.py
from redis.asyncio import Redis as AsyncRedis
from langgraph.checkpoint.redis import AsyncRedisSaver
from redis.asyncio import ConnectionPool
from app.core import config
from app.core import get_custom_logger
logger = get_custom_logger("RedisConnection")

class RedisConnection:
    def __init__(self):
        self._pool = ConnectionPool(
            host=config.redis_host,
            port=config.redis_port,
            password=config.redis_password_str,
            db=config.redis_db,
            max_connections=20,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        self._client = AsyncRedis(connection_pool=self._pool)
        self._redis_checkpoint_saver = AsyncRedisSaver(
            redis_client=self._client,
            ttl={"default_ttl": 600, "refresh_on_read": True},
        )

    
    def get_client(self) -> AsyncRedis:
        """Get Redis client."""
        return self._client

    def get_langgraph_redis_saver(self) -> AsyncRedisSaver:
        """Get LangGraph Redis saver."""
        return self._redis_checkpoint_saver

    async def ping(self) -> bool:
        """Test connection."""
        try:
            return await self._client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False
    
    async def close(self):
        """Close connection pool."""
        await self._client.close()
        await self._pool.disconnect()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

# Singleton instance - created immediately but with pool (non-blocking)
redis_connection: RedisConnection = RedisConnection()