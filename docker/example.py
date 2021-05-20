import redis
import time


def dialog_en_request(question):
    subscriber = redis.StrictRedis(host='localhost', port=6379)
    publisher = redis.StrictRedis(host='localhost', port=6379)
    pub = publisher.pubsub()
    sub = subscriber.pubsub()
    sub.subscribe('dialog_en_client')
    # send
    print('sending')
    publisher.publish("dialog_en_server", question)
    # receive
    print('receiving')
    while True:
        message = sub.get_message()
        if message and message['type']!='subscribe':
            return message['data'].decode("utf-8")
            break
        time.sleep(1)


print(dialog_en_request('Why do you gonna fly to the mars today?'))
print('received')