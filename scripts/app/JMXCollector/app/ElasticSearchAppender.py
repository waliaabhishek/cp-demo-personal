import io
import json
import time
from url_normalize import url_normalize

import requests
from elasticsearch import Elasticsearch

# the url for Elastic connection. No support for SSL yet. maybe some time soon ,
# but need to get the code running first.
es_url = ""
# The index will automatically be created with a date extensions to create index
# per day and keep the clean up easier
#  You will still have to create a read the timestamp in millis ( createdDateTime )
#  in elastic & extract a date from it
es_index_name = ""
# this is the Kibana dashboard URL. This is needed for the initial index, visualization
# and dashboard setup.
kibana_url = ""
kibana_dashboard_file_location = ""
es_bulk_url_timeout_secs = 30


def setup_elastic_connection(elasticsearch_endpoint="http://localhost:9200",
                             elasticsearch_index_name="kafka-jmx-logs",
                             kibana_endpoint="http://localhost:5601",
                             es_bulk_url_timeout=30,
                             kibana_dashboard_filename="scripts/dashboard/jmx_dashboard.json"
                             ):
    global es_url
    global es_index_name
    global kibana_url
    global kibana_dashboard_file_location
    global es_bulk_url_timeout_secs
    es_url = url_normalize(elasticsearch_endpoint)
    es_index_name = elasticsearch_index_name
    kibana_url = url_normalize(kibana_endpoint)
    es_bulk_url_timeout_secs = es_bulk_url_timeout
    kibana_dashboard_file_location = kibana_dashboard_filename
    create_elastic_index_template()


def create_elastic_index_template():
    global es_index_name
    global es_url
    global kibana_url
    global kibana_dashboard_file_location
    # Create first set of headers for inserting the templates
    request_headers = {
        'Content-Type': 'application/json',
    }
    # setup the body for inserting the templates
    data = '{"template": "' + es_index_name + \
        '-*","mappings": {"default": {"properties": {"createdDateTime": {"type": "date"}}}}}'
    # Insert the template into Elastic for datatime formatting
    requests.put(url_normalize(es_url + '/_template/' + es_index_name + '_template'), headers=request_headers,
                 data=data)
    # Setup the headers for inserting index
    request_headers['kbn-version'] = '5.5.2'

    # Create the index pattern for Kibana
    index_creation = '{"title": "' + es_index_name + \
        '-*","notExpandable":true, "timeFieldName": "createdDateTime"}'
    #  insert the index pattern for Kibana
    requests.put(url_normalize(kibana_url + '/es_admin/.kibana/index-pattern/' + es_index_name + '-*/_create'),
                 headers=request_headers, data=index_creation)
    # Parse all the objects in the Dashboard & Visualization file as Kibana 5.5.2 does not have a bulk API for insert.
    # Setup the headers for inserting objects into Kibana
    request_headers['kbn-xsrf'] = 'true'

    with open(kibana_dashboard_file_location, "r") as file:
        file_contents = json.load(file)
        for object_list_values in file_contents:
            requests.put(url_normalize(kibana_url + '/es_admin/.kibana/' + str(object_list_values["_type"]) + "/" + str(
                object_list_values["_id"])), headers=request_headers, json=object_list_values["_source"])


# Creates a file with data to be inserted using ES API.
# The file format is strictly adhering to ES bulk insert and was
# designed to insert in bulk by default.
def internal_write_data_to_file(file_name, json_dict):
    first_run_flag = True
    for item in json_dict:
        if first_run_flag:
            file_name.write("{\"index\":{\"_type\": \"doc\"}}")
            first_run_flag = False
        else:
            file_name.write("\n{\"index\":{\"_type\": \"doc\"}}")
        file_name.write("\n" + str(item))
    return file_name


# Read data from the file and bulk ingest into a specific Elastic index
def call_elastic_bulk(data_dict):
    global es_url
    es_client = Elasticsearch([es_url],
                              retry_on_timeout=True,
                              max_retries=10,
                              timeout=es_bulk_url_timeout_secs)
    # body = []
    in_memory_file_path = io.StringIO("")
    in_memory_file_path = internal_write_data_to_file(
        in_memory_file_path, data_dict)
    # body = file.read().splitlines()
    curr_index_name = es_index_name + "-" + time.strftime("%Y-%m-%d")
    es_client.bulk(body=in_memory_file_path.getvalue(), index=curr_index_name, params={
                   "timeout": str(es_bulk_url_timeout_secs) + "s", "request_timeout": es_bulk_url_timeout_secs})
    in_memory_file_path.close()
    # return response
