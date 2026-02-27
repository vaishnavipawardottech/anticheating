from huey import RedisHuey

# This connects to your Valkey container running on port 6379
huey_queue = RedisHuey('proctoring_events', host='localhost', port=6379)