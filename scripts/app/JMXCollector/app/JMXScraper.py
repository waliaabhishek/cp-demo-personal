from urllib.parse import urlparse
import concurrent.futures
import itertools
import json
import time
import requests

try:
    from . import ReusableCodes as utilitymethods
except ImportError:
    import ReusableCodes as utilitymethods
import ConnectRESTMetrics


CONCURRENT_THREADS = 3
CALL_TIMEOUT_IN_SECS = 45
POLL_WAIT_IN_SECS = 60
IS_CONNECT_REST_ENABLED = False

url_list = {}
default_JMX_fetch = ["/jolokia/read/java.lang:type=*"]
jmx_metrics_data = {}
last_fetch_timestamp = 0


def get_unique_server_list():
    # Setup some variables to work with.
    global url_list
    host_names = []
    dict_hostname_pairs = {}
    splitter_value = "____"
    # Iterate over data and sort out the details
    for server_type, server_list in url_list.items():
        for url in server_list:
            url_details = urlparse(url)
            host_names.append(server_type + splitter_value + str(
                url_details.scheme + "://" + url_details.hostname + ":"
                + str(url_details.port)))
    # Dedupe in a single line ;) -- not so performant , but simpler
    host_names = list(set(host_names))
    # this statement converts the de-duped list into a dict for
    # sending as a response
    for item in host_names:
        dict_hostname_pairs[item.split(splitter_value)[
            1]] = item.split(splitter_value)[0]
    return dict_hostname_pairs


def internal_get_server_type(url):
    global url_list
    return [k for k, v in url_list.items() if url in v][0]


# This function merges data received from get_unique_server_list() function
# and creates logical unique JMX URL's to hit.
def add_default_fetch_list_to_urlist():
    global default_JMX_fetch
    global url_list
    for key, value in url_list.items():
        for filtered_host_URL in [k for k, v in get_unique_server_list().items() if v == key]:
            for default_JMX_fetch_item in default_JMX_fetch:
                value.append(str(filtered_host_URL + default_JMX_fetch_item))
    # De-dupe URL list for all server types
    for i, j in url_list.items():
        url_list[i] = list(set(j))


def setup_everything(input_url_list, input_default_JMX_fetch=default_JMX_fetch, poll_wait=60,
                     thread_count=1, connect_rest_enabled=False, input_call_timeout_in_secs=45):
    global url_list
    global default_JMX_fetch
    global IS_CONNECT_REST_ENABLED
    global POLL_WAIT_IN_SECS
    global CONCURRENT_THREADS
    global CALL_TIMEOUT_IN_SECS

    CONCURRENT_THREADS = thread_count
    CALL_TIMEOUT_IN_SECS = input_call_timeout_in_secs
    POLL_WAIT_IN_SECS = poll_wait
    IS_CONNECT_REST_ENABLED = connect_rest_enabled
    url_list = input_url_list
    default_JMX_fetch = input_default_JMX_fetch
    add_default_fetch_list_to_urlist()


# This function formats the JSON as per our needs and straightens out data
# from a dictionary format to a list format with double quotes on all string
# fields. It also injects some additional data for easing Dashboard setup
def internal_get_structured_json_from_response(jmx_response_data, server_host_name,
                                               server_ID="Default"):
    # Instantiate Empty Lists for storing data
    return_data_set = []
    # formatted_JSON_data_pairs = []
    curr_date_time = utilitymethods.current_milli_time()
    for key, value in jmx_response_data.items():
        formatted_data_KV_pair_strings = []
        if ":" in key:
            formatted_data_header = str(key.split(":")[0])
            formatted_data_KV_pair_strings = key.split(":")[1].split(",")
            value["injectedBeanName"] = formatted_data_header
            value["createdDateTime"] = curr_date_time
            value["injectedServerType"] = server_ID
            value["injectedHostName"] = server_host_name
        else:
            jmx_response_data["createdDateTime"] = curr_date_time
            jmx_response_data["injectedServerType"] = server_ID
            jmx_response_data["injectedHostName"] = server_host_name
            return_data_set.append(json.dumps(jmx_response_data))
            return return_data_set
        for item in range(len(formatted_data_KV_pair_strings)):
            data_KV_pair = formatted_data_KV_pair_strings[item].split("=")
            value[data_KV_pair[0]] = data_KV_pair[1]
        return_data_set.append(json.dumps(value))
    return return_data_set


def internal_prepare_jmx_data_for_url(url, execution_timestamp):
    global CALL_TIMEOUT_IN_SECS
    url_details = urlparse(url)
    server_id = internal_get_server_type(url)
    server_host_name = str(url_details.hostname + ":" + str(url_details.port))
    contents = json.loads(json.dumps(requests.get(
        url, timeout=CALL_TIMEOUT_IN_SECS).json()))['value']
    # print("Data for URL: " + url + " is in format " + str(type(contents)) + ". Data length is " + str(len(contents)) )
    output_JSON_data = internal_get_structured_json_from_response(
        contents, server_host_name, server_ID=server_id)
    return {"target_url": url,
            "execution_timestamp": execution_timestamp,
            "result": output_JSON_data}


def internal_fetch_jmx_data():
    global last_fetch_timestamp
    global jmx_metrics_data
    global url_list
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_THREADS) as executor:
        execution_timestamp = utilitymethods.current_milli_time()
        future_to_url = (executor.submit(internal_prepare_jmx_data_for_url, url,
                                         execution_timestamp) for url in itertools.chain(*url_list.values()))
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                data = future.result()
                jmx_metrics_data[data["target_url"]] = data["result"]
                last_fetch_timestamp = execution_timestamp
            except Exception as exc:
                print(str(exc))
                raise
    if IS_CONNECT_REST_ENABLED:
        connect_rest_object = ConnectRESTMetrics.get_connect_rest_metrics()
        try:
            url_details = urlparse(
                ConnectRESTMetrics.CONNECT_REST_ENDPOINT)
            server_host_name = str(
                url_details.hostname + ":" + str(url_details.port))
            formatted_jmx_data = internal_get_structured_json_from_response(
                connect_rest_object, server_host_name, "KafkaConnect")
            jmx_metrics_data[server_host_name] = formatted_jmx_data
        except Exception as exc:
            print(
                "Connect REST API was not fetched. Ignoring the Connect REST input data.")
            print(str(exc))


def get_metrics(current_timestamp=None, force_metric_collection=False):
    global last_fetch_timestamp
    if current_timestamp is None:
        current_timestamp = utilitymethods.current_milli_time()
    is_metric_fetched = False
    if ((force_metric_collection) or (current_timestamp - last_fetch_timestamp) >= ((POLL_WAIT_IN_SECS - 0.5) * 1000)):
        tic = time.perf_counter()
        internal_fetch_jmx_data()
        is_metric_fetched = True
        toc = time.perf_counter()
        print(f"JMX Metrics Gather Duration : \t\t\t{toc - tic:0.8f} seconds")
    return is_metric_fetched


if __name__ == "__main__":
    # global url_list
    # global POLL_WAIT_IN_SECS
    input_url_list = {"ZooKeeper": ["http://localhost:49901/jolokia/read/org.apache.ZooKeeperService:*"],
                      "KafkaBroker": ["http://localhost:49911/jolokia/read/kafka.*:*",
                                      "http://localhost:49912/jolokia/read/kafka.*:*"],
                      "KafkaConnect": ["http://localhost:49921/jolokia/read/kafka.*:*"]
                      }
    default_JMX_Fetch = ["/jolokia/read/java.lang:type=*"]

    setup_everything(input_url_list, default_JMX_Fetch,
                     poll_wait=20, thread_count=5)
    print(json.dumps(url_list, indent=2))
    runCode = True
    if runCode:
        while(True):
            print("Metrics Gather poll session started at time \t" +
                  time.strftime("%Y-%m-%d %H:%M:%S"))
            # force_collection = bool(random.getrandbits(1))
            if (get_metrics(force_metric_collection=False)):
                print("New data updated in the JMX object. Please retrieve from there")
            else:
                print("No new data received this cycle. Please try again later")
            print("=" * 120)
            time.sleep(POLL_WAIT_IN_SECS)
