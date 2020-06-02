from confluent_kafka import Producer
import json

DEFAULT_TOPIC_NAME = "jmx_data_ingestion_pipeline"
DEFAULT_KAFKA_PRODUCER = ""


def getConfigs(properties):

    # sr_client_props = {
    #     'url': '<CCLOUD_SR_DNS>',
    #     'basic.auth.user.info': '<CCLOUD_SR_KEY>:<CCLOUD_SR_SECRET>'
    # }

    # sr_client = SchemaRegistryClient(sr_client_props)
    # value_serializer = ProtobufSerializer(FoodPreferences_pb2.PersonFood, sr_client)
    if isinstance(properties, dict):
        return properties
    else:
        configs = {
            'bootstrap.servers': 'localhost:12093,localhost:12094',
            'client.id': 'JMX_Data_Producer',
            'compression.type': 'snappy',
            'retries': '10',
            'linger.ms': '50'
        }
        return configs


def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush(). """
    if err is not None:
        print('Message delivery failed: {}'.format(err))


def produce_messages_to_kafka(data_list: list, current_timestamp,
                              producer_object: Producer = DEFAULT_KAFKA_PRODUCER,
                              topic_name: str = DEFAULT_TOPIC_NAME):
    producer_object.poll(0.1)
    for index, item in enumerate(data_list):
        try:
            producer_object.produce(topic=topic_name,
                                    value=json.dumps(item),
                                    on_delivery=delivery_report,
                                    timestamp=current_timestamp)
            if (index % 500 == 0):
                producer_object.flush(0.5)
        except BufferError:
            print('%% Local producer queue is full (%d messages awaiting delivery): flushing...\n' % len(
                producer_object))
            producer_object.flush(0.5)
    producer_object.flush(0.5)
    return True


def setup_kafka_connection(**kwargs):
    global DEFAULT_KAFKA_PRODUCER
    global DEFAULT_TOPIC_NAME
    global PRODUCER_CONFIGS

    DEFAULT_TOPIC_NAME = kwargs["DEFAULT_TOPIC_NAME"]
    PRODUCER_CONFIGS = kwargs["PRODUCER_CONFIGS"]
    DEFAULT_KAFKA_PRODUCER = Producer(getConfigs(PRODUCER_CONFIGS))


if __name__ == "__main__":
    import JMXScraper
    import ReusableCodes
    # global DEFAULT_KAFKA_PRODUCER
    # global DEFAULT_TOPIC_NAME
    DEFAULT_KAFKA_PRODUCER = Producer(getConfigs())
    input_url_list = {"ZooKeeper": ["http://localhost:49901/jolokia/read/org.apache.ZooKeeperService:*"],
                      "KafkaBroker": ["http://localhost:49911/jolokia/read/kafka.*:*",
                                      "http://localhost:49912/jolokia/read/kafka.*:*"],
                      "KafkaConnect": ["http://localhost:49921/jolokia/read/kafka.*:*"]
                      }
    setup_kafka_connection()
    JMXScraper.setup_everything(input_url_list)
    current_timestamp = ReusableCodes.current_milli_time()
    JMXScraper.get_metrics(current_timestamp=current_timestamp)
    for data_node in JMXScraper.jmx_metrics_data:
        produce_messages_to_kafka(data_node, current_timestamp)
