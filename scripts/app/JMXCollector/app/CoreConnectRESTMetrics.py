import requests
import concurrent.futures
import asyncio
import itertools
from requests.auth import HTTPBasicAuth
from urllib3.exceptions import InsecureRequestWarning


AUTH_ENABLED = True
AUTH_TYPE = "basic"
CONCURRENT_THREADS = 3

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


# Async Thread executor for making calls to the REST API.
# The input_uri takes a list of uri as an argument to call and calls them parallely
# The result is returned back as a list of data responses.
async def invoke_urls(input_uri: list, **kwargs):
    return_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_THREADS) as executor:
        future_to_url = (executor.submit(invoke_call, uri, user="superUser",
                                         password="superUser", kwargs=kwargs) for uri in input_uri)
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
def invoke_call(input_uri, **kwargs):
    global CONNECT_REST_ENDPOINT
    global AUTH_ENABLED
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


def generate_metrics_object(connector_status_dict):
    metrics_object = []
    for connector in connectors_status_result:
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


def generate_jmx_metrics_object(generate_metrics_object_result: list):
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


if __name__ == "__main__":
    # Setup the loop to run the REST calls
    loop = asyncio.get_event_loop()
    # Get all deployed connectors
    connectors_list = loop.run_until_complete(invoke_urls([CORE_ENDPOINTS[0]]))
    # Render Connetor REST URI
    connectors_status = [CORE_ENDPOINTS[1].replace(
        "{name}", k) for k in itertools.chain.from_iterable(connectors_list)]
    # Check Connector Status
    connectors_status_result = loop.run_until_complete(
        invoke_urls(connectors_status))

    # Setup a metrics object with all the attributes
    from pprint import pprint as pp
    import json
    output_object = generate_metrics_object(
        connector_status_dict=connectors_status_result)

    # Convert the Data into JMX styled structure used in the JMX Scraper Module
    import JMXScraper
    from urllib.parse import urlparse
    url_details = urlparse(CONNECT_REST_ENDPOINT)
    server_host_name = str(url_details.hostname + ":" + str(url_details.port))
    formmatted_jmx_data = JMXScraper.internal_get_structured_json_from_response(
        generate_jmx_metrics_object(output_object), server_host_name, server_ID="KafkaConnect")
    pp(formmatted_jmx_data, width=400)
    loop.close()
