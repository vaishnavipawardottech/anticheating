from redis import Redis
from rq import Worker, Queue, Connection

# Connect to Redis
redis_conn = Redis(host='localhost', port=6379)

if __name__ == '__main__':
    with Connection(redis_conn):
        # Tell the worker to listen strictly to the "exam_events" queue
        worker = Worker(['exam_events'])
        print("🛠️  Redis Background Worker is listening for exam events...")
        worker.work()