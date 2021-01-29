'''
List all VMs in your subscriptions in a formatted table.
The columns are: VM name, subscription, resource group, size, location, and status.
Each row is a unique VM.

You must login to Azure CLI before you run this script:
$ az login

Usage:
$ python listvms.py -f|--format <format>

Prerequisites:
(env) $ pip install azure-mgmt-resource azure-mgmt-compute azure-identity azure-cli-core tabulate
'''

from azure.mgmt.resource import SubscriptionClient as SubClient
from azure.mgmt.resource import ResourceManagementClient as ResourceClient
from azure.mgmt.compute import ComputeManagementClient as ComputeClient
from azure.mgmt.monitor import MonitorManagementClient as MonitorClient
from azure.identity import AzureCliCredential
import datetime
from operator import itemgetter
from tabulate import tabulate


def sublist(client):
    return [(sub.subscription_id, sub.display_name) for sub in client.subscriptions.list()] 


def grouplist(client):
    return [group.name for group in client.resource_groups.list()]


def vmlist(client, group):
    return [(vm.name, vm.id) for vm in client.virtual_machines.list(group)]


def vmsize(client, group, vm):
    return client.virtual_machines.get(group, vm).hardware_profile.vm_size


def vmlocation(client, group, vm):
    return client.virtual_machines.get(group, vm).location


def vmstatus(client, group, vm):
    ''' 
    Gets the power state of a VM instance. If there is no state to read, returns state = "Unknown".
    '''
    # Sometimes, the instanceview.statuses list is empty or contains only one element.
    # This occurs when a VM fails to deploy properly but also it seems to
    # occasionally for no obvious reason. We check for it and move on.
    try:
        results = client.virtual_machines.instance_view(group, vm).statuses[1].code
    except IndexError:
        return "Unknown"
    # Status code is always a two-part code, divided by a forward-slash.
    # The first is usually "PowerState" and the second is "running" or "deallocated".
    power, state = results.split('/')  
    return state

def calculate_uptime(log):
    start_time = log.event_timestamp
    now = datetime.datetime.now(datetime.timezone.utc)
    uptime = (now - start_time) / datetime.timedelta(hours=1)

    uptime_days = int(uptime) // 24
    uptime_hours = int(uptime) % 24

    if uptime_days == 0:
        uptime = str(uptime_hours) + ' hours'
    else:
        uptime = str(uptime_days) + ' days, '+ str(uptime_hours) + ' hours'

    return uptime


def get_vm_uptime(vm_id, monitor_client):
    '''
    Returns the uptime of an azure VM, using the activity logs, or returns None if it is stopped.
    Because azure only keeps logs for 90 days, uptime can only be found if running for less than 90 days.
    This function written by Ewan Wai (https://www.linkedin.com/in/ewan-wai-7a3905193/)
    '''
    # azure deletes logs that are 90 days old so check from 89 days ago
    # If you filter using a date older than 89 days, you may see an error: "msrest.exceptions.DeserializationError"
    past_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=89)

    
    filter = " and ".join([
        f"eventTimestamp ge '{past_date.date()}T00:00:00Z'",
        f"resourceUri eq '{vm_id}'"
    ])
    
    select = ",".join([
        "operationName",
        "eventTimestamp",
        "status"
    ])

    print(filter)
    print()
    print(select)
    print()

    logs = monitor_client.activity_logs.list( filter=filter, select=select )

    for log in logs:
        print(", ".join([
            log.event_name.value,
            log.operation_name.value,
            log.event_timestamp.isoformat('T'),
            log.status.value
        ]))

    # log_ok = False
    # start_found = False

    # for log in logs:
    #     log_ok = True
    #     # Look for the most recent successful start or creation log (assume VM is running)
    #     vm_started = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/start/action')
    #     vm_created = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/write')
    #     succeeded = (log.status.value == 'Succeeded')
        
    #     if (vm_started or vm_created) and succeeded:
    #         uptime = calculate_uptime(log)
    #         start_found = True
    #         break 

    # # If the loop completes without finding a successful VM start orcreate log,
    # # Assume VM has been running for more than 90 days.

    # # Some VMs' logs are not iterable and the for loop does not run for them so
    # # test that the loop ran at least once by setting log_ok boolean. 

    # if log_ok and start_found:
    #     return uptime
    # elif log_ok and not start_found:
    #     return ">90 days"
    # elif not log_ok and not start_found:
    #     return "Log problem"
    # else:
    #     return "No condition matched" 

    return "Some other error"

def build_vm_list(credentials):
    ''' 
    Build a list of all VMs in all the subscriptions visible to the user.
    The returned list contains nested lists, one header list, and one list
    for each VM. Each nested list contains the VM name, subscription, 
    resource group, size, location, status, and uptime.
    '''
    headers = ['VM name','Subscription','ResourceGroup','Size','Location','Status','Uptime']

    returned_list = list()
    returned_list.append(headers)

    subscription_client = SubClient(credentials)
    subscriptions = sublist(subscription_client)
    for subscription_id, subscription_name in subscriptions:
        resource_client = ResourceClient(credentials, subscription_id)
        resource_groups = grouplist(resource_client)
        for resource_group in resource_groups:
            compute_client = ComputeClient(credentials, subscription_id)
            monitor_client = MonitorClient(credentials, subscription_id)
            vms = vmlist(compute_client, resource_group)
            for vm_name, vm_id in vms:
                vm_status = vmstatus(compute_client, resource_group, vm_name)
                vm_size = vmsize(compute_client, resource_group, vm_name)
                vm_location = vmlocation(compute_client, resource_group, vm_name)
                if vm_status == "running":
                    vm_uptime = get_vm_uptime(vm_id, monitor_client)
                else:
                    vm_uptime = "n/a"
                returned_list.append([vm_name, subscription_name, resource_group, vm_size, vm_location, vm_status, vm_uptime])

    return returned_list


def sort_by_column(input_list, column='Status'):
    ''' Sort a list by the Status field, except for the first row '''

    # To keep this function flexible, search for the index of the
    # 'Status' column in the header row so its index is not hard-coded.
    x = input_list[0].index(column)

    new_list = list()
    new_list.append(input_list[0])
    for row in sorted(input_list[1:], key=itemgetter(x)):
        new_list.append(row)
    return new_list


def print_table(input_list, frmt):
    formatted_table = tabulate(input_list, headers='firstrow', tablefmt=frmt)
    print(formatted_table)


def vm_table(tablefmt,column):
    credentials = AzureCliCredential()
    vm_list = build_vm_list(credentials)
    sorted_list = sort_by_column(vm_list, column)
    print_table(sorted_list, tablefmt)


if __name__ == '__main__':
    vm_table('pretty','Status')   # 'pretty' is one of the formats supported by the tabular library