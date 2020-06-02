import requests
import concurrent.futures
import asyncio
import itertools
from requests.auth import HTTPBasicAuth
from urllib3.exceptions import InsecureRequestWarning
from urllib.parse import urlparse


AUTH_ENABLED = False
AUTH_TYPE = "basic"
CONCURRENT_THREADS = 3
AUTH_USERNAME = "superUser"
AUTH_PASSWORD = "superUser"

JMX_METRICS_BEAN_NAME = 'kafka.connect.api.rest'
JMX_METRICS_TYPE = 'rest-api-metrics'
JMX_METRICS_ATTR_CONNECTOR_NAME = 'connector'
JMX_METRICS_ATTR_CONNECTOR_STATE = 'connector-status'
JMX_METRICS_ATTR_CONNECTOR_TYPE = 'connector-type'

JMX_METRICS_ATTR_TASK_ID = 'task-id'
JMX_METRICS_ATTR_TASK_STATE = 'task-status'
JMX_METRICS_ATTR_TASK_WORKER_ID = 'task-worker-id'

CONNECT_REST_ENDPOINT = "https://localhost:8083"
CORE_ENDPOINTS = ["/connectors",
                  "/connectors/{name}/status"]


def setup_everything(**kwargs):
    global CONNECT_REST_ENDPOINT

    global AUTH_ENABLED
    global AUTH_TYPE
    global AUTH_USERNAME
    global AUTH_PASSWORD
    global CONCURRENT_THREADS
    global JMX_METRICS_BEAN_NAME
    global JMX_METRICS_TYPE

    global JMX_METRICS_ATTR_CONNECTOR_NAME
    global JMX_METRICS_ATTR_CONNECTOR_STATE
    global JMX_METRICS_ATTR_CONNECTOR_TYPE
    global JMX_METRICS_ATTR_TASK_ID
    global JMX_METRICS_ATTR_TASK_STATE
    global JMX_METRICS_ATTR_TASK_WORKER_ID

    CONNECT_REST_ENDPOINT = kwargs.get(
        'CONNECT_REST_ENDPOINT', CONNECT_REST_ENDPOINT)

    AUTH_ENABLED = kwargs.get('AUTH_ENABLED', AUTH_ENABLED)
    AUTH_TYPE = kwargs.get('AUTH_TYPE', AUTH_TYPE)
    AUTH_USERNAME = kwargs.get('AUTH_USERNAME', AUTH_USERNAME)
    AUTH_PASSWORD = kwargs.get('AUTH_PASSWORD', AUTH_PASSWORD)
    CONCURRENT_THREADS = kwargs.get('CONCURRENT_THREADS', CONCURRENT_THREADS)

    JMX_METRICS_BEAN_NAME = kwargs.get(
        'JMX_METRICS_BEAN_NAME', JMX_METRICS_BEAN_NAME)
    JMX_METRICS_TYPE = kwargs.get('JMX_METRICS_TYPE', JMX_METRICS_TYPE)

    JMX_METRICS_ATTR_CONNECTOR_NAME = kwargs.get(
        'JMX_METRICS_ATTR_CONNECTOR_NAME', JMX_METRICS_ATTR_CONNECTOR_NAME)
    JMX_METRICS_ATTR_CONNECTOR_STATE = kwargs.get(
        'JMX_METRICS_ATTR_CONNECTOR_STATE', JMX_METRICS_ATTR_CONNECTOR_STATE)
    JMX_METRICS_ATTR_CONNECTOR_TYPE = kwargs.get(
        'JMX_METRICS_ATTR_CONNECTOR_TYPE', JMX_METRICS_ATTR_CONNECTOR_TYPE)
    JMX_METRICS_ATTR_TASK_ID = kwargs.get(
        'JMX_METRICS_ATTR_TASK_ID', JMX_METRICS_ATTR_TASK_ID)
    JMX_METRICS_ATTR_TASK_STATE = kwargs.get(
        'JMX_METRICS_ATTR_TASK_STATE', JMX_METRICS_ATTR_TASK_STATE)
    JMX_METRICS_ATTR_TASK_WORKER_ID = kwargs.get(
        'JMX_METRICS_ATTR_TASK_WORKER_ID', JMX_METRICS_ATTR_TASK_WORKER_ID)


async def internal_invoke_urls(input_uri: list, **kwargs):
    # Async Thread executor for making calls to the REST API.
    # The input_uri takes a list of uri as an argument to call and calls them parallely
    # The result is returned back as a list of data responses.
    global AUTH_USERNAME
    global AUTH_PASSWORD
    global CONCURRENT_THREADS
    return_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_THREADS) as executor:
        future_to_url = (executor.submit(internal_invoke_call, uri, user=AUTH_USERNAME,
                                         password=AUTH_PASSWORD, kwargs=kwargs) for uri in input_uri)
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                contents = future.result()
                return_data.append(contents)
            except Exception:
                raise
    return return_data


# Invoke the call for the input_uri passed.
# This will setup the request session and calls the url.
# Also does basic auth if AUTH_ENABLED is True.
def internal_invoke_call(input_uri, **kwargs):
    global CONNECT_REST_ENDPOINT
    global AUTH_ENABLED
    global AUTH_TYPE
    session = requests.Session()
    session.verify = kwargs.get('verify', False)
    # Suppress only the single warning from urllib3 needed.
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    if AUTH_ENABLED:
        if "basic" == AUTH_TYPE:
            session.auth = HTTPBasicAuth(kwargs['user'], kwargs['password'])
    else:
        session.auth = None
    try:
        contents = session.get(CONNECT_REST_ENDPOINT + input_uri)
        if contents.ok:
            return contents.json()
    except Exception:
        raise


def internal_generate_metrics_object(connector_status_dict):
    # This function will generate a metrics object which will have attributes and
    # other KV pairs from the REST output
    metrics_object = []
    for connector in connector_status_dict:
        tmp_dict = {}
        tmp_dict[JMX_METRICS_ATTR_CONNECTOR_NAME] = connector['name']
        tmp_dict[JMX_METRICS_ATTR_CONNECTOR_STATE] = connector['connector']['state']
        tmp_dict[JMX_METRICS_ATTR_CONNECTOR_TYPE] = connector['type']
        if len(connector['tasks']) > 0:
            for task in connector['tasks']:
                task_tmp_dict = {}
                task_tmp_dict[str(JMX_METRICS_ATTR_TASK_ID)] = task['id']
                task_tmp_dict[JMX_METRICS_ATTR_TASK_STATE] = task['state']
                task_tmp_dict[JMX_METRICS_ATTR_TASK_WORKER_ID] = task['worker_id']
                task_tmp_dict = {**tmp_dict, **task_tmp_dict}
                metrics_object.append(task_tmp_dict)
        else:
            metrics_object.append(tmp_dict)
    return metrics_object


def internal_generate_jmx_metrics_object(generate_metrics_object_result: list):
    # This function will convert the result from internal metrics object into a JMX compatible
    # daat list for further ingestion. This jmx metrics object can then be directly fed to the
    # JMX scraper data structure and consumer from there.
    jmx_metrics_data = {}
    for item in generate_metrics_object_result:
        key_string = ""
        value_dict = {}
        if JMX_METRICS_ATTR_TASK_ID in item.keys():
            key_string = JMX_METRICS_BEAN_NAME + ":" \
                + "type=" + JMX_METRICS_TYPE + "," \
                + JMX_METRICS_ATTR_CONNECTOR_NAME + "=" + item[JMX_METRICS_ATTR_CONNECTOR_NAME] + "," \
                + JMX_METRICS_ATTR_CONNECTOR_TYPE + "=" + item[JMX_METRICS_ATTR_CONNECTOR_TYPE] + "," \
                + JMX_METRICS_ATTR_TASK_ID + "=" + \
                str(item[JMX_METRICS_ATTR_TASK_ID])
            value_dict[JMX_METRICS_ATTR_CONNECTOR_STATE] = item[JMX_METRICS_ATTR_CONNECTOR_STATE]
            value_dict[JMX_METRICS_ATTR_TASK_STATE] = item[JMX_METRICS_ATTR_TASK_STATE]
            value_dict[JMX_METRICS_ATTR_TASK_WORKER_ID] = item[JMX_METRICS_ATTR_TASK_WORKER_ID]
        else:
            key_string = JMX_METRICS_BEAN_NAME + ":" \
                + "type=" + JMX_METRICS_TYPE + "," \
                + JMX_METRICS_ATTR_CONNECTOR_NAME + "=" + item[JMX_METRICS_ATTR_CONNECTOR_NAME] + "," \
                + JMX_METRICS_ATTR_CONNECTOR_TYPE + "=" + \
                item[JMX_METRICS_ATTR_CONNECTOR_TYPE]
            value_dict[JMX_METRICS_ATTR_CONNECTOR_STATE] = item[JMX_METRICS_ATTR_CONNECTOR_STATE]
        jmx_metrics_data[key_string] = value_dict
    return jmx_metrics_data


def get_connect_rest_metrics(**kwargs):
    global CORE_ENDPOINTS
    # Setup the loop to run the REST calls
    loop = asyncio.get_event_loop()
    # Get all deployed connectors
    connectors_list = loop.run_until_complete(
        internal_invoke_urls([CORE_ENDPOINTS[0]], kwargs))
    # Render Connetor REST URI
    connectors_uri_list = [CORE_ENDPOINTS[1].replace(
        "{name}", k) for k in itertools.chain.from_iterable(connectors_list)]
    # Check Connector Status
    connectors_status_result = loop.run_until_complete(
        internal_invoke_urls(connectors_uri_list, kwargs))
    # Setup a metrics object with all the attributes
    jmx_data = internal_generate_jmx_metrics_object(internal_generate_metrics_object(
        connector_status_dict=connectors_status_result))
    loop.close()
    return jmx_data


if __name__ == "__main__":
    # Setup the loop to run the REST calls
    loop = asyncio.get_event_loop()
    # Get all deployed connectors
    connectors_list = loop.run_until_complete(
        internal_invoke_urls([CORE_ENDPOINTS[0]]))
    # Render Connetor REST URI
    connectors_status = [CORE_ENDPOINTS[1].replace(
        "{name}", k) for k in itertools.chain.from_iterable(connectors_list)]
    # Check Connector Status
    connectors_status_result = loop.run_until_complete(
        internal_invoke_urls(connectors_status))

    # Setup a metrics object with all the attributes
    from pprint import pprint as pp
    output_object = internal_generate_metrics_object(
        connector_status_dict=connectors_status_result)

    # Convert the Data into JMX styled structure used in the JMX Scraper Module
    import JMXScraper
    url_details = urlparse(CONNECT_REST_ENDPOINT)
    server_host_name = str(url_details.hostname + ":" + str(url_details.port))
    formmatted_jmx_data = JMXScraper.internal_get_structured_json_from_response(
        internal_generate_jmx_metrics_object(output_object), server_host_name, server_ID="KafkaConnect")
    pp(formmatted_jmx_data, width=400)
    loop.close()
