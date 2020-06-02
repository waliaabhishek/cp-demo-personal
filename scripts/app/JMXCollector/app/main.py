import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

import ElasticSearchAppender
import JMXScraper
import KafkaAppender

_executor = ThreadPoolExecutor(20)

# I will whole heartily recommend not resolving below 30 seconds as the process needs to execute all the URL's in a
# loop and the Java process will need time to breath , not some other process asking for metrics every 5-10 seconds.
# POLL_WAIT_IN_SECS = 5
# JMX_POLL_CONCURRENT_THREADS = 5

# # The list of endpoints to be farmed. The Structure is a Dictionary with the Server/Component type as the Key and
# # Value is a list of JMX URL's that need to be farmed for those servers.
# url_list = {"ZooKeeper": ["http://localhost:49901/jolokia/read/org.apache.ZooKeeperService:*"],
#             "KafkaBroker": ["http://localhost:49911/jolokia/read/kafka.*:*",
#                             "http://localhost:49912/jolokia/read/kafka.*:*"],
#             "KafkaConnect": ["http://localhost:49921/jolokia/read/kafka.*:*"]
#             }

# Accepted values form ingestion modules are one or more of the following
# "elastic", "kafka"
# Currently only elastic works and others are being worked on.
# ingestion_modules = ["elastic", "kafka"]

# This switch will enable scrape for Connect REST modules and add a new
# JMX metric line for ingestion to all the sources
# enable_connect_rest_scrape = True


async def main_loop(calling_object_method, jmx_data_node):
    task_list = []
    for call_type in calling_object_method:
        for data_node in jmx_data_node.values():
            if "elastic" in call_type:
                task_list.append(loop.run_in_executor(_executor,
                                                      ElasticSearchAppender.call_elastic_bulk, data_node))
            if "kafka" in call_type:
                task_list.append(loop.run_in_executor(_executor, KafkaAppender.produce_messages_to_kafka,
                                                      data_node, JMXScraper.last_fetch_timestamp, KafkaAppender.DEFAULT_KAFKA_PRODUCER))
    await asyncio.gather(*task_list)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Command line arguments for controlling the application", add_help=True, )
    global_args = parser.add_argument_group("global", "Global Arguments")
    jmx_args = parser.add_argument_group(
        "jmx-poll", "JMX Poller module Arguments")
    es_args = parser.add_argument_group(
        "elastic", "Elastic Sink module Arguments")
    kafka_args = parser.add_argument_group(
        "kafka", "Kafka Sink module Arguments")
    connect_rest_args = parser.add_argument_group(
        "connect rest api", "Kafka Connect REST API module Arguments")

    global_args.add_argument('--poll-interval', type=int, default=5,
                             help="Poll Interval to check if JMX metrics are refreshed in the memory or not")
    global_args.add_argument('--thread-count', type=int, default=20,
                             help="Thread pool to create for executing HTTP requests from the code. The HTTP requests include Elastic Bulk requests & Kafka Producer requests.")
    global_args.add_argument('--enable-connect-rest-source', action="store_true",
                             help="Enables the Kafka Connect REST API metrics and publish them as part of the JMX Metrics. Needs configurations for Connect REST API Module Arguments")
    global_args.add_argument('--enable-elastic-sink', action="store_true",
                             help="Enables the Elastic Sink for the JMX metrics. Needs configurations for Elastic Sink Module Arguments")
    global_args.add_argument('--enable-kafka-sink', action="store_true",
                             help="Enables the Elastic Sink for the JMX metrics. Needs configurations for Kafka Sink Module Arguments")

    jmx_args.add_argument('--jmx-poll-thread-count', type=int, default=5,
                          help='Thread pool to fetch JMX metrics. This thread pool is independent from the HTTP call thread pool and is used to fetch the JMX metrics from the servers.')
    jmx_args.add_argument('--jmx-poll-wait-sec', type=int, default=20,
                          help='This is the poll duration which is enacted on JMX module only. The reason is that the poll for any new data from sink modules need to be decoupled from JMX fetch so that we do not overload the jolokia servers. The JMX module runs its own poll and refreshes the data following this particular value. This value cannot be assigned a value below 15 seconds due to overload switch.')
    jmx_args.add_argument('--jmx-poll-timeout', type=int, default=45,
                          help='This parameter will help override the timeout wait for JMX fetch via jolokia.')

    jmx_args.add_argument('--jmx-zk-servers-csv', type=str, default=argparse.SUPPRESS,
                          help='The zookeeper servers comma separated values in the format: http(s)://<hostname>:<port>.  The port number is the exposed Jolokia port for scraping the metrics.')
    jmx_args.add_argument('--jmx-kafka-servers_csv', type=str, default=argparse.SUPPRESS,
                          help='The Apache Kafka servers comma separated values in the format: http(s)://<hostname>:<port>. The port number is the exposed Jolokia port for scraping the metrics.')
    jmx_args.add_argument('--jmx-connect-servers_csv', type=str, default=argparse.SUPPRESS,
                          help='The Apache Kafka Connect servers comma separated values in the format: http(s)://<hostname>:<port>. The port number is the exposed Jolokia port for scraping the metrics.')

    jmx_args.add_argument('--jmx-zk-poll-mbeans-csv', type=str, default=argparse.SUPPRESS,
                          help='The MBeans that will be polled from the ZooKeeper server periodicatlly. The beans follow the formatting conventions required by Jolokia and the service will fail in case the formatting is incorrect. Eg: "org.apache.ZooKeeperService:*"')
    jmx_args.add_argument('--jmx-kafka-poll-mbeans-csv', type=str, default=argparse.SUPPRESS,
                          help='The MBeans that will be polled from the Kafka server periodically. The beans follow the formatting conventions required by Jolokia and the service will fail in case the formatting is incorrect. Eg: "kafka.*:*"')
    jmx_args.add_argument('--jmx-connect-poll-mbeans-csv', type=str, default=argparse.SUPPRESS,
                          help='The MBeans that will be polled from the ZooKeeper server periodicatlly. The beans follow the formatting conventions required by Jolokia and the service will fail in case the formatting is incorrect. Eg: "kafka.*:*"')
    jmx_args.add_argument('--jmx-default-beans-csv', type=str, default="java.lang:type=*",
                          help='The MBeans that will be polled from all the servers periodicatlly. These are common pattern mbeans that you would want to poll from all the servers. The beans follow the formatting conventions required by Jolokia and the service will fail in case the formatting is incorrect. Eg: "java.lang:type=*"')

    connect_rest_args.add_argument('--connect-thread-count', type=int, default=5, required='--enable-connect-rest-source' in sys.argv,
                                   help='Thread pool to fetch Connect REST metrics. This thread pool is independent from the HTTP call thread pool and is used to fetch the Connect REST metrics from the servers.')
    connect_rest_args.add_argument('--connect-rest-endpoint', type=str, default=argparse.SUPPRESS, required='--enable-connect-rest-source' in sys.argv,
                                   help='Connect REST endpoint URL. This is strongly recommended to be the load balanced connect REST URL, so that atleast one of the servers is avaiable all the time.')
    connect_rest_args.add_argument('--enable-connect-rest-auth', action="store_true",
                                   help='Enable authentication for connect REST api poll. Please remember that currently only basic aut is supported.')
    connect_rest_args.add_argument('--connect-rest-auth-user', type=str, default=argparse.SUPPRESS, required='--enable-connect-rest-auth' in sys.argv,
                                   help='Connect basic auth username')
    connect_rest_args.add_argument('--connect-rest-auth-pass', type=str, default=argparse.SUPPRESS, required='--enable-connect-rest-auth' in sys.argv,
                                   help='Connect basic auth password')

    es_args.add_argument('--es-url', type=str, default=argparse.SUPPRESS, required='--enable-elastic-sink' in sys.argv,
                         help='Elastic Search URL for shipping the data to Elastic from this module. Load Balanced URL preferred.')
    es_args.add_argument('--kibana-url', type=str, default=argparse.SUPPRESS, required='--enable-elastic-sink' in sys.argv,
                         help='Kibana URL for creating the dashboards and indexes during the initial setup of the script. Load Balanced URL preferred.')
    es_args.add_argument('--es-bulk-url-timeout', type=int, default=30,
                         help='This parameter controls the timeout for bulk api insertion used by the module. Wont need to change for most cases, but just in case. :) ')

    kafka_args.add_argument('--kafka-topic-name', type=str, default="jmx_data_ingestion_pipeline", required='--enable-kafka-sink' in sys.argv,
                            help='Kafka Topic name for ingesting data from the JMX metrics into. Please remember that this module will produce one message per metric per poll per server. So provision enough partitions and data retention as per requirements.')
    kafka_args.add_argument('--kafka-conn-props', required='--enable-kafka-sink' in sys.argv, action="append", dest="kafka_connection",
                            help='One key value per prop switch. All of them will be added to the kafka producer connection.')

    args = parser.parse_args()
    print(args)
    connection_props = dict()
    if args.kafka_connection:
        for item in args.kafka_connection:
            k, v = item.split("=", 1)
            connection_props[k] = v

    import itertools

    def return_url_set(list1, list2):
        if None not in (list1, list2):
            return list(k[0] + "/jolokia/read/" + k[1]
                        for k in itertools.product(list1.split(","), list2.split(",")))
        else:
            return None

    url_list = dict()
    url_list["ZooKeeper"] = return_url_set(args.zk_servers_csv,
                                           args.zk_poll_mbeans_csv)
    url_list["KafkaBroker"] = return_url_set(args.args.kafka_servers_csv,
                                             args.kafka_poll_mbeans_csv)
    url_list["KafkaConnect"] = return_url_set(args.args.connect_servers_csv,
                                              args.connect_poll_mbeans_csv)
    default_JMX_URLs = return_url_set(list("/jolokia/read/"),
                                      args.jmx_default_beans_csv)

    POLL_WAIT_IN_SECS = args.poll_interval
    ingestion_modules = []
    if args.enable_elastic_sink:
        ingestion_modules.append("elastic")
    if args.enable_kafka_sink:
        ingestion_modules.append("kafka")

    JMXScraper.setup_everything(url_list, default_JMX_URLs,
                                poll_wait=(15 if args.jmx_poll_wait_sec < 15
                                           else args.jmx_poll_wait_sec),
                                thread_count=args.jmx_poll_thread_count,
                                connect_rest_enabled=args.enable_connect_rest_source,
                                input_call_timeout_in_secs=args.jmx_poll_timeout)
    print(json.dumps(JMXScraper.url_list, indent=2))
    if args.enable_elastic_sink:
        ElasticSearchAppender.setup_elastic_connection(elasticsearch_endpoint=args.es_url,
                                                       elasticsearch_index_name="kafka-jmx-logs",
                                                       kibana_endpoint=args.kibana_url,
                                                       es_bulk_url_timeout=args.es_bulk_url_timeout)
    if args.enable_kafka_sink:
        KafkaAppender.setup_kafka_connection(DEFAULT_TOPIC_NAME=args.kafka_topic_name,
                                             PRODUCER_CONFIGS=connection_props)
    if args.enable_connect_rest_source:
        import ConnectRESTMetrics
        ConnectRESTMetrics.setup_everything(CONNECT_REST_ENDPOINT=args.connect_rest_endpoint,
                                            CONCURRENT_THREADS=4,
                                            AUTH_ENABLED=args.enable_connect_rest_auth,
                                            AUTH_USERNAME=args.connect_rest_auth_user,
                                            AUTH_PASSWORD=args.connect_rest_auth_pass)
    runCode = True
    if runCode:
        loop = asyncio.get_event_loop()
        while (True):
            print("Metrics Gather poll session started at time \t" +
                  time.strftime("%Y-%m-%d %H:%M:%S"))
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
