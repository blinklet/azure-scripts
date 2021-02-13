'''
List all VMs in your subscriptions in a formatted table.
The columns are: VM name, subscription, resource group, size, location, and status.
Each row is a unique VM.

You must login to Azure CLI before you run this script:
$ az login

Prerequisites:
(env) $ pip install azure-mgmt-resource azure-mgmt-compute azure-identity \
        azure-cli-core tabulate azure-mgmt-monitor
'''

from azure.mgmt.resource import SubscriptionClient as SubClient
from azure.mgmt.resource import ResourceManagementClient as ResourceClient
from azure.mgmt.compute import ComputeManagementClient as ComputeClient
from azure.mgmt.monitor import MonitorManagementClient as MonitorClient
from azure.identity import DefaultAzureCredential
from datetime import datetime, timezone, timedelta
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
    # occasionally occur for no obvious reason. We check for it and move on.
    try:
        results = client.virtual_machines.instance_view(group, vm).statuses[1].code
    except IndexError:
        return 'Unknown'

    # Status code is always a two-part code, divided by a forward-slash.
    # The first is usually "PowerState" and the second is "running" or "deallocated".
    power, state = results.split('/')  
    return state


def diff_time(start_time):
    now = datetime.now(timezone.utc)
    uptime = (now - start_time) / timedelta(hours=1)

    uptime_days = int(uptime) // 24
    uptime_hours = int(uptime) % 24

    if uptime_days == 0:
        uptime = str(uptime_hours) + ' hours'
    else:
        uptime = str(uptime_days) + ' days, '+ str(uptime_hours) + ' hours'

    return uptime


def get_vm_time(vm_id, monitor_client, switch='up'):
    '''
    Similiar to get_uptime function, but looks for most recent shutdown log
    '''
    # If you filter using a date older than 89 days, you may see 
    # an error message like: "msrest.exceptions.DeserializationError"
    past_date = datetime.now(timezone.utc) - timedelta(days=89)

    filter = " and ".join([
        f"eventTimestamp ge '{past_date.date()}T00:00:00Z'",
        f"resourceUri eq '{vm_id}'"
    ])
    
    select = ','.join([
        'operationName',
        'eventTimestamp',
        'status'
    ])

    logs = monitor_client.activity_logs.list(filter=filter, select=select)

    for log in logs:
        if switch == 'down':
            # Look for the most recent successful deallocation log
            vm_deallocated = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/deallocate/action')
            succeeded = (log.status.value == 'Succeeded')
            
            if vm_deallocated and succeeded:
                return diff_time(log.event_timestamp)

        elif switch == 'up':
            # Look for the most recent successful start or creation log
            vm_started = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/start/action')
            vm_created = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/write')
            succeeded = (log.status.value == 'Succeeded')
            
            if (vm_started or vm_created) and succeeded:
                return diff_time(log.event_timestamp)

        else:
            return "invalid switch"  # to catch programming errors 

    # If the loop completes without finding a successful VM start or create log,
    # or if the logs iterator is empty (so loop does not execute), 
    # VM has been running for more than 90 days.
    return '>90 days'


def build_vm_list(credentials):
    ''' 
    Build a list of all VMs in all the subscriptions visible to the user.
    The returned list contains nested lists, one header list, and one list
    for each VM. Each nested list contains the VM name, subscription, 
    resource group, size, location, status, and uptime.
    '''
    headers = ['VM name','Subscription','ResourceGroup','Size','Location','Status','TimeInState']

    returned_list = list()
    returned_list.append(headers)

    subscription_client = SubClient(credentials)
    subscriptions = sublist(subscription_client)

    for subscription_id, subscription_name in subscriptions:
        resource_client = ResourceClient(credentials, subscription_id)
        compute_client = ComputeClient(credentials, subscription_id)
        monitor_client = MonitorClient(credentials, subscription_id)
        resource_groups = grouplist(resource_client)

        for resource_group in resource_groups:
            vms = vmlist(compute_client, resource_group)

            for vm_name, vm_id in vms:

                vm_status = vmstatus(compute_client, resource_group, vm_name)
                vm_size = vmsize(compute_client, resource_group, vm_name)
                vm_location = vmlocation(compute_client, resource_group, vm_name)

                if vm_status == 'running':
                    vm_time = get_vm_time(vm_id, monitor_client, switch="up")
                elif vm_status == "deallocated":
                    vm_time = get_vm_time(vm_id, monitor_client, switch="down")
                elif vm_status == 'Unknown':
                    vm_time = 'Unknown'
                else:
                    vm_time = '???'  # if unexpected result

                returned_list.append([
                    vm_name, 
                    subscription_name, 
                    resource_group, 
                    vm_size, 
                    vm_location, 
                    vm_status, 
                    vm_time
                ])

    return returned_list


def sort_by_column(input_list, *sort_keys):
    ''' Sort a list by columns, except for the first row '''
    
    headers = input_list[0]
    list_to_sort = input_list[1:]
    x = [headers.index(column) for column in sort_keys]

    list_to_sort.sort(key=itemgetter(*x))
    list_to_sort.insert(0, headers)
    return list_to_sort


def vm_table():
    credentials = DefaultAzureCredential(
        exclude_environment_credential = True,
        exclude_managed_identity_credential = True,
        exclude_shared_token_cache_credential = True,
        exclude_visual_studio_code_credential = True,
        exclude_interactive_browser_credential = False
    )
    vm_list = build_vm_list(credentials)

    if len(vm_list) > 1:
        sorted_list = sort_by_column(vm_list,'Status','ResourceGroup','Size')
        formatted_table = tabulate(sorted_list, headers='firstrow', tablefmt="pretty")
        return formatted_table
    else:
        return "No VMs found"

def main():
    print(vm_table())

if __name__ == '__main__':
    main()
    