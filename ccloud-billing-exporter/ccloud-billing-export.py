import json
import time
import requests
import configargparse

from datetime import *
from dateutil.relativedelta import *
from requests.exceptions import HTTPError

def key_billing_data(data):
    key = {'id': data['resource']['id'],
           'start_date': data['start_date'],
           'granularity': data['granularity']}
    return json.dumps(key)

def request_params(args):
    if args.start_date is not None and args.end_date is not None:
        start_date = args.start_date
        end_date = args.end_date
    elif args.month is not None:
        s = datetime.strptime(args.month, '%Y-%m').replace(day=1)
        e = s + relativedelta(months=+1)
        start_date = s.strftime('%Y-%m-%d')
        end_date = e.strftime('%Y-%m-%d')
    else:
        raise Exception("Start and end dates or a month must be defined. Start dates are formatted YYYY-MM-DD, "
                        "Month is formatted YYYY-MM")
    
    params = {
        'start_date': start_date,
        'end_date': end_date
    }

    try:
        params['page_size'] = args.page_size
    except AttributeError:
        pass
    return params

def main(args):
    # Metrics
    start_time = datetime.now()    
    api_request_counter = 0
    data_row_counter = 0
    produce_to_kafka_counter = 0

    print('Confluent Billing Exporter')
    print('Start time:', start_time.strftime('%Y-%m-%d %H:%M:%S'))

    # Set the key and value serialisers
    splunk_hec_url = "https://splunk-ccloud:8088/services/collector/event"
    splunk_hec_headers = {"Authorization": "Splunk " + args.spl_hec_token}
    splunk_hec_index = 'ccloud-billing'

    # Create the initial request to the REST API. Subsequent requests will use the pagination feature
    response = requests.get(args.rest_url,
                            params=request_params(args),
                            auth=(args.rest_api_key, args.rest_api_secret))
    api_request_counter += 1

    next_url = 'This is not empty, so we will run at least once'
    backoff_time = 0

    while next_url:

        try:
            if response.status_code == 200:
                backoff_time = 0
                billing_response = response.json()
                billing_data = billing_response['data']
                next_url = billing_response['metadata']['next']
                data_row_counter += len(billing_data)

                # Iterate billing_data and produce to Kafka
                for data in billing_data:
                    key = key_billing_data(data)
                    spl_response = requests.post(
                        url=splunk_hec_url, headers=splunk_hec_headers, 
                        json={"index": splunk_hec_index, "event": data}, 
                        verify=False)
                    
            elif response.status_code == 429:
                backoff_time += 1
                print(
                    f'Confluent Cloud Rate Limit exceeded, backing off for {backoff_time} seconds')
                time.sleep(backoff_time)
            else:
                raise HTTPError(response.status_code)

            if next_url:
                response = requests.get(next_url, auth=(args.rest_api_key, args.rest_api_secret))
                api_request_counter += 1

        except KeyboardInterrupt:
            break
        except HTTPError as e:
            if response.status_code == 400:
                r = response.json()
                for e in r['errors']:
                    print(f'HTTP error: {e}')
            else:
                print(f'HTTP error: {e}')
            break
        except ValueError as e:
            print(f"Value Error: {e}")
            break

    end_time = datetime.now()
    duration = end_time - start_time
    print("End time:", end_time.strftime("%Y-%m-%d %H:%M:%S"))
    print("Duration:", duration, "seconds")
    print('Read', data_row_counter, 'data items from the REST API in ', api_request_counter, 'requests')

# main()
if __name__ == '__main__':
    p = configargparse.ArgParser(default_config_files=['settings.properties'])
    # Arguments for config files
    p.add_argument('--file',
                   is_config_file=True,
                   help='Path to a file containing properties',
                   env_var='CCLOUD_BE_CONFIG_FILE')
    
    # Arguments from settings.propperities
    p.add_argument('--rest-url',
                   default='https://api.confluent.cloud/billing/v1/costs',
                   help='The url of the Confluent Billing REST API',
                   env_var='CCLOUD_BE_REST_URL')
    p.add_argument('--rest-api-key',
                   required=True,
                   help='A Confluent Cloud API Key for a user with the Organization Admin rolebinding',
                   env_var='CCLOUD_BE_REST_API_KEY')
    p.add_argument('--rest-api-secret',
                   required=True,
                   help='The API Secret corresponding to the API Key',
                   env_var='CCLOUD_BE_REST_API_SECRET')
    p.add_argument('--start-date',
                   # required=True,
                   help='The start date for the export',
                   env_var='CCLOUD_BE_START_DATE')
    p.add_argument('--end-date',
                   # required=True,
                   help='The end date for the export',
                   env_var='CCLOUD_BE_END_DATE')
    p.add_argument('--page-size',
                   help='The number of line items to return in a single reqeust',
                   env_var='CCLOUD_BE_PAGE_SIZE')
    p.add_argument('--month',
                   help='A single month to export, in the format YYYY-MM. Ignored if dates are supplied.',
                   env_var='CCLOUD_BE_MONTH')
    p.add_argument('--spl-hec-url',
                   help='The Splunk HEC URL to post the data to.',
                   env_var='CCLOUD_BE_SPL_HEC_TOKEN')
    p.add_argument('--spl-hec-token',
                   help='A Splunk HEC token to ingest the data with.',
                   env_var='CCLOUD_BE_SPL_HEC_TOKEN')
    p.add_argument('--spl-hec-index',
                   help='A Splunk index to ingest the data into.',
                   env_var='CCLOUD_BE_SPL_HEC_INDEX')

    main(p.parse_args())