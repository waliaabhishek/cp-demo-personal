import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

import ElasticSearchAppender
import JMXScraper
import KafkaAppender

# I will whole heartily recommend not resolving below 30 seconds as the process needs to execute all the URL's in a
# loop and the Java process will need time to breath , not some other process asking for metrics every 5-10 seconds.
POLL_WAIT_IN_SECS = 5
JMX_POLL_CONCURRENT_THREADS = 5
_executor = ThreadPoolExecutor(20)

# The list of endpoints to be farmed. The Structure is a Dictionary with the Server/Component type as the Key and
# Value is a list of JMX URL's that need to be farmed for those servers.
url_list = {"ZooKeeper": ["http://localhost:49901/jolokia/read/org.apache.ZooKeeperService:*"],
            "KafkaBroker": ["http://localhost:49911/jolokia/read/kafka.*:*",
                            "http://localhost:49912/jolokia/read/kafka.*:*"],
            "KafkaConnect": ["http://localhost:49921/jolokia/read/kafka.*:*"]
            }
default_JMX_URLs = ["/jolokia/read/java.lang:type=*"]

# Accepted values form ingestion modules are one or more of the following
# "elastic", "kafka"
# Currently only elastic works and others are being worked on.
ingestion_modules = ["elastic"]


async def main_loop(calling_object_method, jmx_data_node):
    task_list = []
    for call_type in calling_object_method:
        for data_node in jmx_data_node.values():
            if "elastic" in call_type:
                task_list.append(loop.run_in_executor(
                    _executor, ElasticSearchAppender.call_elastic_bulk, data_node))
            if "kafka" in call_type:
                task_list.append(loop.run_in_executor(_executor, KafkaAppender.produce_messages_to_kafka,
                                                      data_node, JMXScraper.last_fetch_timestamp, KafkaAppender.DEFAULT_KAFKA_PRODUCER))
    await asyncio.gather(*task_list)
    # if "elastic" in calling_object_method:
    #     start_time = time.perf_counter()
    #     print("Ingestion into Elastic started at time " + time.strftime("%Y-%m-%d %H:%M:%S"))
    #     for data_node in jmx_data_node.values():
    #         await loop.run_in_executor(_executor, ElasticSearchAppender.call_elastic_bulk, data_node)
    #         await loop.run_in_executor(_executor, KafkaAppender.produce_messages_to_kafka, data_node, JMXScraper.last_fetch_timestamp, KafkaAppender.DEFAULT_KAFKA_PRODUCER)
    #     end_time = time.perf_counter() - start_time
    #     print(f"Ingestion into Elastic finished in {end_time:0.2f} seconds.")


if __name__ == "__main__":
    JMXScraper.setup_everything(url_list, default_JMX_URLs,
                                poll_wait=(30 if POLL_WAIT_IN_SECS <
                                           30 else POLL_WAIT_IN_SECS),
                                thread_count=JMX_POLL_CONCURRENT_THREADS)
    print(json.dumps(JMXScraper.url_list, indent=2))
    if ("elastic" in ingestion_modules):
        ElasticSearchAppender.setup_elastic_connection()
    if ("kafka" in ingestion_modules):
        KafkaAppender.setup_kafka_connection()
    runCode = True
    if runCode:
        loop = asyncio.get_event_loop()
        while (True):
            print("Metrics Gather poll session started at time \t" +
                  time.strftime("%Y-%m-%d %H:%M:%S"))
            # force_collection = bool(random.random() > 0.5)
            if (JMXScraper.get_metrics(force_metric_collection=False)):
                print("New data updated in the JMX object. Please retrieve from there")
                start_time = time.perf_counter()
                loop.run_until_complete(
                    main_loop(ingestion_modules, JMXScraper.jmx_metrics_data))
                end_time = time.perf_counter() - start_time
                print(
                    f"Ingestion comnplete cycle finished in {end_time:0.2f} seconds.")

            else:
                print("No new data received this cycle.Please try again later")
            print("=" * 120)
            time.sleep(POLL_WAIT_IN_SECS)
        loop.close()
